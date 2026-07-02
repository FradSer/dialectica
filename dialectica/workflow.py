"""Workflow orchestration primitives — a composable multi-agent runtime.

A Python re-implementation of the orchestration surface Claude Code's ``Workflow``
tool provides, built on this repo's single LLM seam (``agent_runtime.run_agent``).
It exists so arbitrary multi-agent workflows — research, review, design,
planning, the *meta-task* regime where generate -> adversarial-judge ->
synthesize genuinely helps — can be expressed as plain Python instead of
hardcoded into one fixed engine loop.

The primitives:

  * ``agent(prompt, *, schema=None, tools=None, instructions="", label=None,
    phase=None, model=None)`` — one LLM call; ``schema`` (a Pydantic model)
    forces structured JSON output and returns the validated instance. ``tools``
    wires plain callables into this call the same way the demoted agentic
    pattern (``examples/patterns/agentic_pattern.py``) does, so
    a stage can act (read a file, run a command) instead of only rearranging
    the model's own text — ADK forbids combining ``tools`` with ``schema`` on
    one call, so mix them across stages, not within one. ``instructions``
    appends task-specific system-prompt framing (e.g. an "act, don't guess"
    charter for a tool-using stage). ``model`` accepts a ``"provider:model"``
    override, resolved the same way every other roster call site in this repo
    resolves it. Returns ``None`` on terminal skip or unparseable output after
    retry, so a failed agent never kills its batch (``.filter(None)`` the
    results, as in the JS Workflow).
  * ``parallel(thunks)`` — run a list of zero-arg coroutines concurrently and
    WAIT for all (a barrier). Exceptions in any thunk -> ``None`` in the result
    list; the call itself never rejects.
  * ``pipeline(items, *stages)`` — run each item through every stage with NO
    barrier between stages (item A can be in stage 3 while item B is still in
    stage 1). A stage that throws drops that item to ``None`` and skips its
    remaining stages. This is the DEFAULT multi-stage shape.
  * ``phase(title)`` — mark a progress group (for rendering only; no gate).
  * ``log(msg)`` — emit a progress line.
  * ``budget`` — a ``Budget`` with ``total`` / ``spent()`` / ``remaining()``;
    ``agent()`` raises ``BudgetExhausted`` if a total is set and exhausted.
    ``Workflow(budget_total=..., budget_unit="tokens")`` gates on API-reported
    output tokens (thinking included) instead of call counts; both meters
    always accumulate — ``spent_calls()`` / ``spent_tokens()`` / ``usage()``.

HONEST SCOPE: on *self-contained result-quality* tasks, no multi-agent scaffold
in this repo beats a prompt-matched single call (see README Evaluation — the
ToT+GAN engine goes 0-4-1 / 0-2-3 / 0-1-4 vs single / best-of-N / self-refine;
flat self-refine is best). This module is an **orchestration layer for
meta-tasks** (no ground truth, exploratory/judgmental — research, review,
planning, design), NOT a self-contained-quality engine. The existing negative
findings stand; composing a workflow over these primitives does not repeal
them. ``agent(tools=...)`` is the one lever that can: a stage that reads a
real file or runs a real command is grounded the way the agentic pattern is, not a
pure-LLM rearrangement — but only if the caller actually injects tools. A
workflow built entirely from schema-only judge/synthesize stages is still
pure-LLM and still bound by the findings above.

Example — a 3-angle research fan-out + synthesis (mocked in tests):

    async def script():
        phase("Gather")
        angles = ["broad", "skeptical", "practitioner"]
        findings = await parallel(
            lambda: agent(f"Research angle: {a}") for a in angles
        )
        phase("Synthesize")
        return await agent(
            "Synthesize: " + " | ".join(f for f in findings if f)
        )

    result = await Workflow(script).run()

Resume / journaling is NOT implemented in v1 (documented gap); nested
``workflow()`` calls are single-level only, matching the Workflow tool rule.
"""

import asyncio
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from . import agent_runtime
from .agent_factory import create_agent
from .agent_runtime import TokenUsage
from .json_repair import repair_json_escapes, strip_code_fence
from .llm_config import _parse_model_config, get_model_config

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cap overlapping agent() calls. The Workflow tool caps concurrent agent()
# calls (excess calls queue) — the semaphore is acquired inside agent() around
# each underlying LLM call, so parallel/pipeline branches doing non-LLM work
# never hold a slot. The cap is min(16, cpu-2), overridable via
# DIALECTICA_WORKFLOW_CONCURRENCY or the Workflow(concurrency=...) arg.
_DEFAULT_CONCURRENCY = max(1, min(16, (os.cpu_count() or 4) - 2))


class BudgetExhausted(RuntimeError):
    """Raised by ``agent()`` when a budget total is set and exhausted."""


@dataclass
class Budget:
    """Call/token budget for a workflow run.

    ``unit`` selects what ``total`` means and what ``spent()``/``remaining()``
    report: ``"calls"`` (default) counts ``agent()`` calls; ``"tokens"``
    counts API-reported output tokens (thinking included — the Workflow
    tool's unit). Both meters always accumulate regardless of unit —
    ``spent_calls()``, ``spent_tokens()`` and ``usage()`` expose them for
    observability even when no total is set. The gate fires at ``agent()``
    entry: once ``spent()`` reaches ``total``, further calls raise
    ``BudgetExhausted`` (a token total can be overshot by the call in flight;
    the next call throws). The pool is per-workflow-run, shared across all
    branches — global, not per-branch. Mocked responses without usage
    metadata (plain strs through the ``run_agent`` seam) meter as zero
    tokens.
    """

    total: int | None = None
    unit: str = "calls"
    _calls: int = field(default=0, init=False, repr=False)
    _prompt_tokens: int = field(default=0, init=False, repr=False)
    _output_tokens: int = field(default=0, init=False, repr=False)
    _total_tokens: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.unit not in ("calls", "tokens"):
            raise ValueError(
                f"unknown budget unit {self.unit!r}: use 'calls' or 'tokens'"
            )

    def spent(self) -> int:
        return self._calls if self.unit == "calls" else self._output_tokens

    def spent_calls(self) -> int:
        return self._calls

    def spent_tokens(self) -> int:
        return self._output_tokens

    def usage(self) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self._prompt_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._total_tokens,
        )

    def remaining(self) -> float:
        return float("inf") if self.total is None else max(0, self.total - self.spent())

    def _charge(self) -> None:
        if self.total is not None and self.spent() >= self.total:
            noun = "agent calls" if self.unit == "calls" else "output tokens"
            raise BudgetExhausted(
                f"Workflow budget exhausted: {self.spent()}/{self.total} {noun}."
            )
        self._calls += 1

    def _record(self, usage: TokenUsage) -> None:
        self._prompt_tokens += usage.prompt_tokens
        self._output_tokens += usage.output_tokens
        self._total_tokens += usage.total_tokens


# --- Run context (ContextVar so nested asyncio tasks see the same context) ---


@dataclass
class _RunCtx:
    budget: Budget
    phases: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    concurrency: int = _DEFAULT_CONCURRENCY
    semaphore: asyncio.Semaphore | None = None
    args: Any = None


_current: ContextVar[_RunCtx | None] = ContextVar(
    "dialectica_workflow_ctx", default=None
)


def _ctx() -> _RunCtx:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "Workflow primitives (agent/parallel/pipeline/phase/log/budget) can "
            "only be called inside a Workflow script. See Workflow.run()."
        )
    return ctx


def _to_identifier(label: str) -> str:
    """Coerce a free-form label to a valid Python identifier for LlmAgent.name.

    ADK rejects names containing non-identifier chars (``:`` in
    ``"angle:skeptical"``); the label is for logs, so sanitize it here.
    """
    sanitized = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in label)
    if not sanitized or not sanitized[0].isalpha() and sanitized[0] != "_":
        sanitized = "_" + sanitized
    return sanitized


# --- Primitives -----------------------------------------------------------


def phase(title: str) -> None:
    """Mark a progress group (rendering only; no synchronization gate)."""
    ctx = _ctx()
    ctx.phases.append(title)
    logger.info("[workflow phase] %s", title)


def log(message: str) -> None:
    """Emit a progress line to the run log and the module logger."""
    ctx = _ctx()
    ctx.log.append(message)
    logger.info("[workflow] %s", message)


def budget() -> Budget:
    """The run's ``Budget`` — ``spent()`` / ``remaining()`` / ``total``."""
    return _ctx().budget


def args() -> Any:
    """The ``args`` value passed to ``Workflow(...)``, verbatim."""
    return _ctx().args


def in_workflow() -> bool:
    """True when called inside an active ``Workflow`` script context.

    Lets an engine that wraps its own ``Workflow`` script (e.g. repair) join
    an outer run instead of opening a fresh context, so its calls share the
    outer budget and concurrency cap — the Workflow tool's child-workflow rule.
    """
    return _current.get() is not None


async def agent(
    prompt: str,
    *,
    schema: Type[BaseModel] | None = None,
    tools: list[Any] | None = None,
    instructions: str = "",
    label: str | None = None,
    phase: str | None = None,  # noqa: A002 — mirrors the Workflow tool's opt name
    model: str | None = None,
    max_attempts: int = 3,
) -> Any:
    """One LLM call. Returns the model's text, or a validated ``schema`` instance.

    With ``schema`` set, the agent uses ADK ``output_schema`` for enforced JSON
    and the result is validated into the Pydantic model; a transiently
    empty/malformed response is re-asked up to ``max_attempts`` times, then
    returns ``None`` (a failed agent must not kill its batch). Without ``schema``
    the raw text is returned. ``tools`` wires plain callables (or ADK
    ``FunctionTool``s) into this call's agent so it can act — read a file, run
    a command, query a service — the same wiring the demoted agentic pattern
    (``examples/patterns/agentic_pattern.py``) uses; ADK forbids combining
    ``tools`` with ``schema`` on one ``LlmAgent``, so passing both raises
    ``ValueError`` (run a tool-using stage first, then a separate
    ``schema``-only stage to structure its result). ``instructions`` appends
    task-specific framing to the agent's system prompt (e.g. "act, don't
    guess — verify with tools"), the same role the agentic pattern's system
    prompt plays, without needing a separate engine class. ``model`` overrides the
    model for this call only (``"openai:qwen3.6-flash"`` style, resolved the
    same way every other roster call site in this repo resolves it; ``None``
    inherits the session default).
    """
    if tools and schema is not None:
        raise ValueError(
            "agent() cannot combine tools with schema — ADK forbids tools + "
            "output_schema on one LlmAgent. Run a tool-using stage (no schema) "
            "first, then a separate schema-only stage to structure its result."
        )

    ctx = _ctx()
    ctx.budget._charge()
    if phase:
        ctx.phases.append(phase)

    # ADK requires LlmAgent.name to be a valid Python identifier; the user's
    # ``label`` is free-form ("angle:skeptical", "verify:3") and is for
    # logging/tracing, so sanitize it for the agent name and keep the label
    # verbatim only where it surfaces to logs.
    name = _to_identifier(label) if label else "WorkflowAgent"
    agent_obj = create_agent(
        role="Generator",
        role_name=name,
        additional_context=instructions,
        model_config=_parse_model_config(model)
        if model
        else get_model_config("GENERATOR"),
        tools=tools,
        output_schema=schema,
    )

    # Some OpenAI-compatible backends (DashScope/qwen) reject `response_format:
    # json_object` unless the word "json" appears in the prompt. The repo hits
    # this same constraint in gan_evaluator's build_discriminator_instruction;
    # mirror it here so `agent(schema=...)` works across backends.
    if schema is not None and "json" not in prompt.lower():
        prompt = prompt + "\n\nReturn your answer as a single JSON object."

    # The run's concurrency cap gates each underlying LLM call here — not in
    # parallel/pipeline — so a branch idling in non-LLM work holds no slot.
    # Each response's API-reported usage (if the transport attached any) is
    # metered onto the run's budget, re-asks included.
    sem = ctx.semaphore

    async def _call() -> str:
        if sem is None:
            response = await agent_runtime.run_agent(agent_obj, prompt)
        else:
            async with sem:
                response = await agent_runtime.run_agent(agent_obj, prompt)
        usage = getattr(response, "usage", None)
        if usage is not None:
            ctx.budget._record(usage)
        return response

    response = await _call()

    if schema is None:
        return response

    # Structured-output path: validate, re-asking on transient parse failure.
    for attempt in range(1, max_attempts + 1):
        result = _parse_structured(response, schema)
        if result is not None:
            return result
        if attempt < max_attempts:
            logger.warning(
                "agent(%s) unparseable structured output, re-asking %d/%d",
                label or "agent",
                attempt + 1,
                max_attempts,
            )
            response = await _call()
    logger.warning(
        "agent(%s) returning None after %d parse failures", label, max_attempts
    )
    return None


def _parse_structured(response: str, schema: Type[BaseModel]) -> BaseModel | None:
    """Parse an LLM JSON response into ``schema``, tolerating fences/escapes.

    Models in schema mode often wrap the JSON object in narration or a markdown
    fence ("Here is the result: ```json {...} ```"). ``strip_code_fence`` only
    handles the case where the WHOLE body is fenced, so we additionally extract
    the first balanced ``{...}`` object and try every candidate.
    """
    if not response:
        return None
    candidates = _extract_json_candidates(response)
    for body in candidates:
        for candidate in (body, repair_json_escapes(body)):
            try:
                return schema.model_validate_json(candidate)
            except ValidationError:
                continue
            except ValueError:
                continue
    return None


def _extract_json_candidates(response: str) -> list[str]:
    """Yield plausible JSON-object substrings to try, most specific first.

    Order: the fenced body if any, then the first balanced ``{...}`` span,
    then the stripped whole response as a last resort.
    """
    candidates: list[str] = []
    fenced = strip_code_fence(response).strip()
    if fenced:
        candidates.append(fenced)
    span = _first_json_object_span(response)
    if span is not None:
        candidates.append(response[span[0] : span[1]])
    candidates.append(response.strip())
    # Dedup while preserving order.
    seen: set[str] = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def _first_json_object_span(text: str) -> tuple[int, int] | None:
    """Return (start, end) indices of the first balanced top-level ``{...}``."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return (start, i + 1)
        start = text.find("{", start + 1)
    return None


async def parallel(thunks: Sequence[Callable[[], Awaitable[Any]]]) -> list[Any]:
    """Run zero-arg coroutines concurrently and WAIT for all (a barrier).

    A thunk that raises (or whose awaited value raises) resolves to ``None``;
    the call never rejects. Filter with ``[x for x in res if x is not None]``.
    Thunks hold no concurrency slot themselves — the run's cap gates the
    ``agent()`` calls inside them.
    """
    _ctx()  # primitives are only valid inside a Workflow script

    async def _run(thunk: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await thunk()
        except Exception as e:  # noqa: BLE001 —Workflow contract: failure -> null
            logger.warning("parallel thunk failed: %s", e)
            return None

    return await asyncio.gather(*(_run(t) for t in thunks))


async def pipeline(
    items: Sequence[Any], *stages: Callable[[Any, Any, int], Awaitable[Any]]
) -> list[Any]:
    """Run each item through every stage with NO barrier between stages.

    Item A can be in stage 3 while item B is still in stage 1 — wall-clock is
    the slowest single-item chain, not the sum of slowest-per-stage. Each stage
    callback receives ``(prev_result, original_item, index)``; use
    ``original_item``/``index`` to label work without threading context through
    stage 1's return value. A stage that throws drops that item to ``None`` and
    skips its remaining stages. The run's concurrency cap gates the ``agent()``
    calls inside stages, not whole item chains — an item idling in a non-LLM
    stage holds no slot.
    """
    _ctx()  # primitives are only valid inside a Workflow script

    async def _chain(item: Any, index: int) -> Any:
        try:
            prev = item
            for stage in stages:
                prev = await stage(prev, item, index)
            return prev
        except Exception as e:  # noqa: BLE001 — pipeline contract: failure -> null
            logger.warning("pipeline item %d dropped: %s", index, e)
            return None

    return await asyncio.gather(*(_chain(it, i) for i, it in enumerate(items)))


# --- Entry point -----------------------------------------------------------


class Workflow:
    """Executes a workflow script with the primitives in scope.

    The script is a zero-arg coroutine that calls ``agent``/``parallel``/
    ``pipeline``/``phase``/``log``/``budget``/``args`` as module-level names —
    they resolve to the current run's context via ``ContextVar``, so nested
    ``asyncio`` tasks (created by ``parallel``/``pipeline``) see the same
    budget and log.
    """

    def __init__(
        self,
        script: Callable[[], Awaitable[Any]],
        *,
        args: Any = None,
        budget_total: int | None = None,
        budget_unit: str = "calls",
        concurrency: int | None = None,
    ):
        self.script = script
        self._args = args
        self._budget_total = budget_total
        self._budget_unit = budget_unit
        self._concurrency = concurrency

    async def run(self) -> Any:
        cap = (
            self._concurrency
            or int(os.environ.get("DIALECTICA_WORKFLOW_CONCURRENCY", "0") or "0")
            or _DEFAULT_CONCURRENCY
        )
        ctx = _RunCtx(
            budget=Budget(total=self._budget_total, unit=self._budget_unit),
            concurrency=cap,
            semaphore=asyncio.Semaphore(cap),
            args=self._args,
        )
        token = _current.set(ctx)
        try:
            return await self.script()
        finally:
            _current.reset(token)


__all__ = [
    "Workflow",
    "Budget",
    "BudgetExhausted",
    "agent",
    "parallel",
    "pipeline",
    "phase",
    "log",
    "budget",
    "args",
    "in_workflow",
]
