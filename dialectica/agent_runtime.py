"""Single entry point for invoking an LlmAgent.

Centralizing the ADK Runner call gives every pluggable component (generator,
evaluator, synthesizer) one shared seam — which is also the one place tests
patch to run the engine without the network.

``run_agent`` retries transient failures with exponential backoff: an engine
run is hundreds of sequential LLM calls, and without retry a single network
error or rate limit throws the whole run away. Persistent failures re-raise.
"""

import asyncio
import logging
import os
import random
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from typing import Self
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import (
    InvocationContext,
    LlmCallsLimitExceededError,
)
from google.adk.apps.app import App
from google.adk.events import Event, EventActions
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.runners import InMemoryRunner

from .adk_config import (
    ensure_otel_setup,
    get_context_cache_config,
    get_run_config,
    reset_adk_config_state,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenUsage:
    """API-reported token counts for one or more LLM calls.

    ``output_tokens`` includes thinking tokens (billed as output). Token counts
    include only reported usage; ``unknown_calls`` counts model attempts with
    no final usage metadata, so missing reports are not presented as known zero cost.
    ``model_calls`` counts ADK model turns observed before dispatch, including
    runtime retries and cache short circuits. It does not count hidden SDK or
    provider-internal retries, and is distinct from workflow agent steps.
    """

    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    unknown_calls: int = 0
    model_calls: int = 0


class AgentResponse(str):
    """The agent's text output, carrying the call's ``TokenUsage``.

    A ``str`` subclass so every consumer of the ``run_agent`` seam — and every
    test fake that returns a plain str — keeps working unchanged; metering
    callers read ``.usage``.
    """

    usage: TokenUsage

    def __new__(cls, text: str, usage: TokenUsage) -> "Self":
        obj = super().__new__(cls, text)
        obj.usage = usage
        return obj

    def __getnewargs__(self) -> tuple:  # str's default drops ``usage`` on pickle
        return (str(self), self.usage)


def _usage_from_events(events: Iterable[Event]) -> TokenUsage:
    """Sum ``usage_metadata`` across a run's events.

    One event per LLM turn — a tool-using call produces several. Events
    without metadata (e.g. function-call events) count as zero.

    Output tokens: native Gemini reports ``candidates_token_count`` EXCLUDING
    thoughts, but ADK's LiteLLM mapping sets it to ``completion_tokens`` —
    which already INCLUDES reasoning — and reports ``thoughts_token_count`` on
    top. Naively summing both double-counts reasoning on ``openai:`` roster
    models, so when a total is reported, thoughts are clamped to the room the
    totals actually leave (``total - prompt - candidates``); Gemini's totals
    leave exactly ``thoughts``, LiteLLM's leave zero.
    """
    prompt = output = total = cached = 0
    for event in events:
        um = event.usage_metadata
        if um is None:
            continue
        event_prompt = um.prompt_token_count or 0
        candidates = um.candidates_token_count or 0
        thoughts = um.thoughts_token_count or 0
        event_total = um.total_token_count or 0
        if event_total and thoughts:
            thoughts = min(thoughts, max(0, event_total - event_prompt - candidates))
        prompt += event_prompt
        output += candidates + thoughts
        total += event_total
        cached += um.cached_content_token_count or 0
    return TokenUsage(
        prompt_tokens=prompt,
        output_tokens=output,
        total_tokens=total,
        cached_tokens=cached,
    )


def _combine_usage(*usages: TokenUsage) -> TokenUsage:
    return TokenUsage(
        **{f.name: sum(getattr(u, f.name) for u in usages) for f in fields(TokenUsage)}
    )


@dataclass
class _UsageTracker:
    events: list[Event | None] = field(default_factory=list)
    slots: dict[int, int] = field(default_factory=dict)
    actions: list[EventActions] = field(default_factory=list)
    complete: set[int] = field(default_factory=set)

    @property
    def calls(self) -> int:
        return len(self.events)

    def usage(self) -> TokenUsage:
        return _combine_usage(
            _usage_from_events(event for event in self.events if event is not None),
            TokenUsage(
                model_calls=self.calls, unknown_calls=self.calls - len(self.complete)
            ),
        )

    def reconcile(self, events: Iterable[Event]) -> None:
        """Short-circuit before-model responses bypass the after-model hook."""
        for event in events:
            slot = self.slots.get(id(event.actions))
            if (
                slot is not None
                and self.events[slot] is None
                and event.usage_metadata is not None
            ):
                self.events[slot] = event
                if not event.partial:
                    self.complete.add(slot)


_active_usage: ContextVar[_UsageTracker | None] = ContextVar(
    "dialectica_usage", default=None
)


class _UsagePlugin(BasePlugin):
    """Observe reported usage before ADK builds events or executes tools."""

    def __init__(self) -> None:
        super().__init__(name="dialectica_usage")

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> None:
        tracker = _active_usage.get()
        if tracker is not None:
            key = id(callback_context.actions)
            tracker.slots[key] = tracker.calls
            tracker.events.append(None)
            # Keep actions alive so later turns cannot reuse their object IDs.
            tracker.actions.append(callback_context.actions)

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        tracker = _active_usage.get()
        if tracker is not None and llm_response.usage_metadata is not None:
            key = id(callback_context.actions)
            slot = tracker.slots.get(key)
            if slot is not None:
                # A final cumulative report replaces partials for the same request.
                tracker.events[slot] = Event(
                    author="usage", usage_metadata=llm_response.usage_metadata
                )
                if not llm_response.partial:
                    tracker.complete.add(slot)

    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ) -> None:
        tracker = _active_usage.get()
        if tracker is not None:
            # Cache short circuits skip after_model; observe their events eagerly.
            tracker.reconcile([event])


# Optional global cap on concurrent LLM calls, for tightly-quota'd backends
# (e.g. gemma-4-31b allows only 16k input tokens/minute — unbounded gather
# self-collides on the quota). 0 or unset = unlimited.
_concurrency_limiter: asyncio.Semaphore | None = None
_limiter_configured = False


def _reset_concurrency_limiter() -> None:
    """Re-read DIALECTICA_MAX_CONCURRENCY on next call (used by tests)."""
    global _concurrency_limiter, _limiter_configured
    _concurrency_limiter = None
    _limiter_configured = False


def _get_concurrency_limiter() -> asyncio.Semaphore | None:
    global _concurrency_limiter, _limiter_configured
    if not _limiter_configured:
        _limiter_configured = True
        cap = int(os.environ.get("DIALECTICA_MAX_CONCURRENCY", "0") or "0")
        if cap > 0:
            _concurrency_limiter = asyncio.Semaphore(cap)
    return _concurrency_limiter


def _make_runner(agent: LlmAgent) -> InMemoryRunner:
    """Build an ADK runner, optionally wiring context caching via ``App``."""
    cache_config = get_context_cache_config()
    app = App(
        name="dialectica",
        root_agent=agent,
        context_cache_config=cache_config,
        plugins=[_UsagePlugin()],
    )
    return InMemoryRunner(app=app, app_name="dialectica")


def _reset_adk_runtime_state() -> None:
    """Re-read ADK env config on next call (tests only)."""
    reset_adk_config_state()


@dataclass
class _RunnerScope:
    runner: InMemoryRunner | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)


_runner_scope: ContextVar[_RunnerScope | None] = ContextVar(
    "dialectica_runner_scope", default=None
)


async def _call_agent_once(agent: LlmAgent, instruction: str) -> str:
    """One raw ADK invocation, returning the concatenated text output.

    The return value is an ``AgentResponse`` — a str carrying the call's
    summed ``TokenUsage`` for metering callers.
    """
    ensure_otel_setup()
    run_config = get_run_config()
    scope = _runner_scope.get()
    runner = scope.runner if scope else None
    if runner is None:
        runner = _make_runner(agent)
        if scope is not None:
            scope.runner = runner
    tracker = _UsageTracker()
    usage_token = _active_usage.set(tracker)
    try:
        events = await runner.run_debug(
            instruction,
            session_id=uuid4().hex,
            quiet=True,
            run_config=run_config,
        )
    except BaseException as error:
        error.dialectica_usage = tracker.usage()
        raise
    finally:
        _active_usage.reset(usage_token)
        # run_agent owns the runner across retries; standalone calls own it here.
        if scope is None:
            try:
                await runner.close()
            except BaseException as error:
                error.dialectica_usage = tracker.usage()
                raise

    tracker.reconcile(events)
    response_text = ""
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not part.thought:
                    response_text += part.text

    return AgentResponse(
        response_text.strip(),
        tracker.usage() if tracker.calls else _usage_from_events(events),
    )


# Rate-limit quotas (e.g. tokens-per-minute) need the window to roll over;
# exponential backoff in seconds just burns the remaining attempts.
RATE_LIMIT_COOLDOWN = 45.0
MAX_RATE_LIMIT_RETRIES = 8

_RATE_LIMIT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "rate limit", "RateLimit")


def _is_rate_limited(error: Exception) -> bool:
    text = str(error)
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _is_permanent_failure(error: Exception) -> bool:
    """Separate rejected requests/billing from recoverable capacity limits."""
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status in {400, 401, 402, 403, 404, 405, 422}:
        return True
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "api_key_invalid",
            "invalid api key",
            "unknown provider for model",
            "insufficient_quota",
            "billing_hard_limit_reached",
            "subscription expired",
            "coding plan expired",
            "subscription has expired",
            "套餐已到期",
        )
    )


async def run_agent(
    agent: LlmAgent,
    instruction: str,
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> str:
    """Run ``agent`` on ``instruction``, retrying transient failures.

    Rate-limit errors (429/RESOURCE_EXHAUSTED) have their own retry budget
    (``MAX_RATE_LIMIT_RETRIES``) and wait ``RATE_LIMIT_COOLDOWN`` (scaled,
    jittered to desynchronize concurrent callers) so the quota window can
    roll over; other failures use ``max_attempts`` with fast exponential
    backoff. ``DIALECTICA_MAX_CONCURRENCY`` caps overlapping calls globally.
    From the real transport the returned str is an ``AgentResponse`` whose
    ``.usage`` carries API-reported token counts; a plain str (e.g. from a
    test fake) simply meters as zero. Reported usage includes failed attempts;
    final exceptions expose ``dialectica_usage``. ``unknown_calls`` counts
    model attempts for which no final usage metadata was received.
    """
    scope = _RunnerScope()
    token = _runner_scope.set(scope)
    try:
        return await _run_agent_with_retries(
            agent, instruction, max_attempts=max_attempts, base_delay=base_delay
        )
    except BaseException as error:
        error.dialectica_usage = scope.usage
        raise
    finally:
        try:
            if scope.runner is not None:
                await scope.runner.close()
        except BaseException as error:
            error.dialectica_usage = scope.usage
            raise
        finally:
            _runner_scope.reset(token)


async def _run_agent_with_retries(
    agent: LlmAgent, instruction: str, *, max_attempts: int, base_delay: float
) -> str:
    limiter = _get_concurrency_limiter()
    failures = 0
    rate_limit_hits = 0
    accumulated = TokenUsage()
    while True:
        try:
            if limiter is not None:
                async with limiter:
                    response = await _call_agent_once(agent, instruction)
            else:
                response = await _call_agent_once(agent, instruction)
            usage = _combine_usage(
                accumulated, getattr(response, "usage", TokenUsage())
            )
            if scope := _runner_scope.get():
                scope.usage = usage
            return AgentResponse(str(response), usage)
        except BaseException as e:
            accumulated = _combine_usage(
                accumulated, getattr(e, "dialectica_usage", TokenUsage())
            )
            e.dialectica_usage = accumulated
            if scope := _runner_scope.get():
                scope.usage = accumulated
            if not isinstance(e, Exception) or isinstance(
                e, LlmCallsLimitExceededError
            ):
                raise
            if _is_permanent_failure(e):
                raise
            if _is_rate_limited(e):
                rate_limit_hits += 1
                if rate_limit_hits > MAX_RATE_LIMIT_RETRIES:
                    raise
                delay = RATE_LIMIT_COOLDOWN * min(rate_limit_hits, 3)
                delay += random.uniform(0, 10)
                logger.warning(
                    "Rate limited (hit %d/%d), cooling down %.1fs",
                    rate_limit_hits,
                    MAX_RATE_LIMIT_RETRIES,
                    delay,
                )
            else:
                failures += 1
                if failures >= max_attempts:
                    raise
                delay = base_delay * 2 ** (failures - 1)
                logger.warning(
                    "Agent call failed (attempt %d/%d), retrying in %.1fs: %s",
                    failures,
                    max_attempts,
                    delay,
                    e,
                )
            await asyncio.sleep(delay)
