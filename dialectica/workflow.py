"""Embeddable Python workflow kernel with explicit reliability boundaries.

agent() is a workflow step, potentially containing multiple model turns.
parallel/pipeline settle all siblings and raise BatchFailed by default; collect
and explicit legacy modes preserve a partial Workflow.report. sees= selects only
named prior outputs and is a context convenience, not an authority boundary.

Resume requires a host-managed resume_version plus stable code/input/tool/model
fingerprints. External effects require versioned verification before reuse or
explicit idempotent rerun authorization. Worktrees expose task-local paths;
tools, OS sandboxing and external acceptance checks belong to the host.
"""

import asyncio
import inspect
import logging
import os
import traceback
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel, ValidationError

from . import agent_runtime
from .agent_factory import create_agent
from .agent_runtime import TokenUsage
from .json_repair import repair_json_escapes, strip_code_fence
from .llm_config import _parse_model_config, get_model_config
from .tool_policy import enforce_tools
from .workflow_journal import (
    _MAX_AGENT_CALLS,
    _MAX_ITEM_CAP,
    RunJournal,
    agent_cache_key,
    default_journal_dir,
    deserialize_agent_result,
    journal_lock,
    serialize_agent_result,
)
from .workflow_registry import (
    get_workflow as _get_registered_workflow,
)
from .workflow_registry import (
    list_workflows,
    register_workflow,
)
from .workflow_worktree import WorkflowWorktreeError, worktree_path, worktree_session

logger = logging.getLogger(__name__)

T = TypeVar("T")
P = ParamSpec("P")

# Cap overlapping agent() calls. The Workflow tool caps concurrent agent()
# calls (excess calls queue) — the semaphore is acquired inside agent() around
# each underlying LLM call, so parallel/pipeline branches doing non-LLM work
# never hold a slot. The cap is min(16, cpu-2), overridable via
# DIALECTICA_WORKFLOW_CONCURRENCY or the Workflow(concurrency=...) arg.
_DEFAULT_CONCURRENCY = max(1, min(16, (os.cpu_count() or 4) - 2))


class BudgetExhausted(RuntimeError):
    """Raised by ``agent()`` when a budget total is set and exhausted."""


class WorkflowMetaError(ValueError):
    """Raised when ``meta`` is invalid or phases do not match ``phase()`` calls."""


class WorkflowAgentCapExceeded(RuntimeError):
    """Raised when a run exceeds the lifetime agent() cap (1000)."""


class ResumeUnsafeError(RuntimeError):
    """A prior effectful step needs host reconciliation before it may run again."""


@dataclass(frozen=True)
class ItemOutcome:
    index: int
    status: str
    value: Any = None
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None
    completed_stages: int = 0


class BatchFailed(RuntimeError):
    """All siblings have settled; outcomes preserve successes and failure evidence."""

    def __init__(self, outcomes: list[ItemOutcome]):
        self.outcomes = outcomes
        super().__init__(
            f"{sum(o.status == 'failed' for o in outcomes)} batch items failed"
        )


@dataclass
class WorkflowReport:
    run_id: str
    status: str = "running"
    value: Any = None
    outcomes: list[ItemOutcome] = field(default_factory=list)
    error: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    agent_steps: int = 0


@dataclass
class Budget:
    """Per-invocation admission meters, shared by all branches and child workflows.

    calls counts admitted agent steps, not model turns. tokens gates reported
    output tokens (including reported thinking). Already running invocations can
    overshoot; queued dispatch and structured re-asks recheck the gate. Unknown
    usage blocks further token-budget admission. Neither meter caps dollars.
    model_turn_limit separately caps observed ADK before-model admissions,
    including tool loops/retries/cache shortcuts, excluding hidden SDK retries.
    Cached replay costs no new steps/tokens; usage.jsonl retains prior receipts.
    """

    total: int | None = None
    unit: str = "calls"
    _calls: int = field(default=0, init=False, repr=False)
    _prompt_tokens: int = field(default=0, init=False, repr=False)
    _output_tokens: int = field(default=0, init=False, repr=False)
    _total_tokens: int = field(default=0, init=False, repr=False)
    _cached_tokens: int = field(default=0, init=False, repr=False)
    _unknown_calls: int = field(default=0, init=False, repr=False)
    _model_calls: int = field(default=0, init=False, repr=False)
    model_turn_limit: int | None = None
    _admitted_model_turns: int = field(default=0, init=False, repr=False)

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
            cached_tokens=self._cached_tokens,
            unknown_calls=self._unknown_calls,
            model_calls=self._model_calls,
        )

    def remaining(self) -> float:
        return float("inf") if self.total is None else max(0, self.total - self.spent())

    def _check(self) -> None:
        if self.total is not None and self.unit == "tokens" and self._unknown_calls:
            raise BudgetExhausted("Token budget cannot admit work after unknown usage")
        if self.total is not None and self.spent() >= self.total:
            noun = "agent calls" if self.unit == "calls" else "output tokens"
            raise BudgetExhausted(
                f"Workflow budget exhausted: {self.spent()}/{self.total} {noun}."
            )

    def _charge(self) -> None:
        self._check()
        self._calls += 1

    def _admit_model_turn(self) -> None:
        if (
            self.model_turn_limit is not None
            and self._admitted_model_turns >= self.model_turn_limit
        ):
            raise agent_runtime.ModelTurnLimitExceeded(
                "Workflow model-turn limit reached"
            )
        self._admitted_model_turns += 1

    def _record(self, usage: TokenUsage) -> None:
        self._prompt_tokens += usage.prompt_tokens
        self._output_tokens += usage.output_tokens
        self._total_tokens += usage.total_tokens
        self._cached_tokens += usage.cached_tokens
        self._unknown_calls += usage.unknown_calls
        self._model_calls += usage.model_calls


# --- Run context (ContextVar so nested asyncio tasks see the same context) ---


@dataclass
class _RunCtx:
    budget: Budget
    run_id: str
    journal: RunJournal
    journal_path: Path
    phases: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    concurrency: int = _DEFAULT_CONCURRENCY
    semaphore: asyncio.Semaphore | None = None
    args: Any = None
    depth: int = 0
    agent_sequence: int = 0
    replay_decisions: list[asyncio.Event] = field(default_factory=list)
    registry_name: str | None = None
    meta: dict[str, Any] | None = None
    # Per-step access-list store: label -> str(result). Populated by agent()
    # after each call so a later agent(sees=[label]) can read its output as
    # prior context. Fugu-Ultra-style isolation: default is "own transcript
    # only"; sees= opts in to designated prior step outputs.
    step_outputs: dict[str, str] = field(default_factory=dict)
    outcomes: list[ItemOutcome] = field(default_factory=list)


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
    if not sanitized or (not sanitized[0].isalpha() and sanitized[0] != "_"):
        sanitized = "_" + sanitized
    return sanitized


def _validate_meta(meta: dict[str, Any]) -> None:
    if not meta.get("name") or not meta.get("description"):
        raise WorkflowMetaError("meta requires 'name' and 'description'")


def _check_meta_phases(ctx: _RunCtx) -> None:
    if not ctx.meta:
        return
    declared = [
        p.get("title")
        for p in ctx.meta.get("phases", [])
        if isinstance(p, dict) and p.get("title")
    ]
    if not declared:
        return
    if ctx.phases != declared:
        raise WorkflowMetaError(
            f"meta phases {declared!r} do not match phase() calls {ctx.phases!r}"
        )


def run_id() -> str:
    """The current run's id (for resume/journaling)."""
    return _ctx().run_id


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


def _record_agent_failure(
    call: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    @wraps(call)
    async def recorded(*args: P.args, **kwargs: P.kwargs) -> T:
        ctx = _ctx()
        sequence = ctx.agent_sequence
        try:
            return await call(*args, **kwargs)
        except BaseException as error:
            ctx.outcomes.append(
                ItemOutcome(
                    sequence,
                    "failed",
                    error_type=type(error).__name__,
                    error=str(error),
                    traceback=traceback.format_exc(),
                )
            )
            raise

    return recorded


_verifying_cache: ContextVar[bool] = ContextVar("verifying_cache", default=False)


@_record_agent_failure
async def agent(
    prompt: str,
    *,
    schema: type[BaseModel] | None = None,
    tools: list[Any] | None = None,
    instructions: str = "",
    label: str | None = None,
    phase: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
    isolation: str | None = None,
    agent_type: str | None = None,
    sees: list[str] | None = None,
    replay_version: str | None = None,
    verify_cached: Callable[[Any], bool | Awaitable[bool]] | None = None,
    replay: str = "verify",
) -> Any:
    """One LLM call. Returns the model's text, or a validated ``schema`` instance.

    With ``schema`` set, the agent uses ADK ``output_schema`` for requested JSON
    and the result is validated into the Pydantic model; a transiently
    empty/malformed response is re-asked up to ``max_attempts`` times, then
    returns ``None`` and marks the run partial. Tool-bearing steps never
    automatically re-ask or retry an entire invocation because effects may recur. Without ``schema``
    the raw text is returned. ``tools`` wires plain callables (or ADK
    ``FunctionTool``s) into this call's agent so it can act — read a file, run
    a command, query a service — the same wiring the demoted agentic pattern
    (``examples/patterns/agentic_pattern.py``) uses. ``tools`` and ``schema``
    can be combined: ADK uses model capabilities to select native structured
    output or a response-tool fallback. ``instructions`` appends
    task-specific framing to the agent's system prompt (e.g. "act, don't
    guess — verify with tools"), the same role the agentic pattern's system
    prompt plays, without needing a separate engine class. ``model`` overrides the
    model for this call only (``"openai:qwen3.6-flash"`` style, resolved the
    same way every other roster call site in this repo resolves it; ``None``
    inherits the session default). ``sees`` is a per-step access list of prior
    step labels (``sees=["gather", "critique"]``): the *outputs* of those
    prior steps (looked up by their ``label=``) are appended to this call's
    prompt as prior context, and only those — the default (``None``) is full
    isolation, an agent never sees another agent's transcript. Unknown labels
    are ignored, so an access list survives conditional branches. This is the
    Fugu-Ultra anti-collapse lever (see module docstring): selective context
    visibility, opt-in, no training required.
    """
    if _verifying_cache.get():
        raise RuntimeError("verify_cached must not invoke workflow agents")
    if isolation is not None and isolation != "worktree":
        raise ValueError(
            f"unknown isolation {isolation!r}: only 'worktree' is supported"
        )

    ctx = _ctx()
    if ctx.agent_sequence >= _MAX_AGENT_CALLS:
        raise WorkflowAgentCapExceeded(
            f"Workflow agent cap exceeded: {_MAX_AGENT_CALLS} agent() calls per run."
        )

    if verify_cached is not None and not replay_version:
        raise ValueError("verify_cached requires an explicit replay_version")
    if replay not in ("verify", "rerun"):
        raise ValueError("replay must be 'verify' or explicit 'rerun'")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    enforce_tools(tools or [], agent_type)
    resolved_model = (
        _parse_model_config(model)
        if model is not None
        else get_model_config("GENERATOR")
    )
    effective_prompt = prompt
    if sees:
        blocks = [ctx.step_outputs[name] for name in sees if name in ctx.step_outputs]
        if blocks:
            effective_prompt = (
                "Prior context from named steps:\n"
                + "\n---\n".join(blocks)
                + "\n---\n\nTask:\n"
                + prompt
            )
    cache_key = agent_cache_key(
        effective_prompt,
        schema=schema,
        tools=tools,
        instructions=instructions,
        label=label,
        phase=phase,
        model=resolved_model,
        isolation=isolation,
        agent_type=agent_type,
        sees=sees,
        replay_version=replay_version,
        max_attempts=max_attempts,
    )
    sequence = ctx.agent_sequence
    # Reserve before awaiting a host verifier as well as before live model calls.
    ctx.agent_sequence += 1
    # Every tool may consult mutable external state; all tool/worktree calls
    # require host reconciliation, including steps interrupted before completion.
    effectful = bool(tools) or isolation is not None
    prior_effect = ctx.journal.resuming and sequence in ctx.journal.effectful_sequences
    # Verifiers may overlap, but a cached suffix cannot commit before all
    # earlier decisions. Waiting on every event also preserves ordering when
    # an intermediate decision fails or is cancelled.
    earlier_decisions = tuple(ctx.replay_decisions)
    decision = asyncio.Event()
    ctx.replay_decisions.append(decision)
    try:
        cached = ctx.journal.lookup(sequence, cache_key)
        reusable = False
        result: Any = None
        if cached is not None and replay != "rerun":
            result = deserialize_agent_result(cached, schema)
            reusable = not effectful and not prior_effect
            if verify_cached is not None and replay_version:
                token = _verifying_cache.set(True)
                try:
                    verdict = verify_cached(result)
                    if inspect.isawaitable(verdict):
                        verdict = await verdict
                    reusable = verdict is True
                except Exception:  # noqa: BLE001 — failed validation forbids reuse
                    reusable = False
                finally:
                    _verifying_cache.reset(token)
        for earlier in earlier_decisions:
            await earlier.wait()
        if reusable and ctx.journal.lookup(sequence, cache_key) is cached:
            if phase:
                ctx.phases.append(phase)
            _store_step_output(ctx, label, result)
            return result
        # A rejected or unavailable prefix invalidates every cached suffix,
        # including when external effects prevent an automatic rerun.
        ctx.journal.invalidate_from(sequence)
        if prior_effect and replay != "rerun":
            raise ResumeUnsafeError(
                f"Step {sequence} has prior external effects or observations; "
                "supply a versioned verify_cached returning True, or explicitly "
                "authorize replay='rerun' with host-managed idempotency"
            )
    except BaseException:
        ctx.journal.invalidate_from(sequence)
        raise
    finally:
        decision.set()
    ctx.budget._charge()
    if effectful:
        ctx.journal.effectful_sequences.add(sequence)
    # Persist intent before dispatch, so a process death never hides a started tool.
    pending = serialize_agent_result(None, schema)
    pending.sequence, pending.cache_key, pending.prompt = sequence, cache_key, prompt
    pending.result_kind = "pending"
    ctx.journal.append(pending)
    ctx.journal.persist(ctx.journal_path)
    step_usage = Budget()
    if phase:
        ctx.phases.append(phase)

    worktree_note = ""
    if isolation == "worktree":
        worktree_note = (
            "\n\nYou are running in an isolated git worktree. "
            "Tools must use that explicit path; this is not an OS sandbox."
        )

    name = _to_identifier(label) if label else "WorkflowAgent"

    async def _execute_agent() -> Any:
        agent_obj = create_agent(
            role="Generator",
            role_name=name,
            additional_context=instructions
            + worktree_note
            + (f"\nAbsolute worktree path: {worktree_path.get()}" if isolation else ""),
            model_config=resolved_model,
            tools=tools,
            output_schema=schema,
            agent_type=agent_type,
        )

        call_prompt = effective_prompt
        # The JSON-format instruction is gated on the *task* prompt (not the
        # prior-context-augmented effective_prompt): an injected prior output
        # that happens to mention "json" must not suppress the schema
        # formatting instruction and risk prose -> parse failure.
        if schema is not None and "json" not in prompt.lower():
            call_prompt = (
                call_prompt + "\n\nReturn your answer as a single JSON object."
            )

        sem = ctx.semaphore

        async def _call() -> str:
            try:
                if sem is None:
                    if ctx.budget.unit == "tokens":
                        ctx.budget._check()
                    response = await agent_runtime.run_agent(agent_obj, call_prompt)
                else:
                    async with sem:
                        if ctx.budget.unit == "tokens":
                            ctx.budget._check()
                        response = await agent_runtime.run_agent(agent_obj, call_prompt)
            except BaseException as error:
                usage = getattr(
                    error,
                    "dialectica_usage",
                    None
                    if isinstance(error, BudgetExhausted)
                    else TokenUsage(unknown_calls=1),
                )
                if usage is not None:
                    ctx.budget._record(usage)
                    step_usage._record(usage)
                    ctx.journal.record_usage(
                        ctx.journal_path, sequence, usage, failed=True
                    )
                raise
            usage = getattr(response, "usage", TokenUsage(unknown_calls=1))
            if usage is not None:
                ctx.budget._record(usage)
                step_usage._record(usage)
                ctx.journal.record_usage(
                    ctx.journal_path, sequence, usage, failed=False
                )
            return response

        response = await _call()

        if schema is None:
            return response

        attempts = 1 if tools else max_attempts
        for attempt in range(1, attempts + 1):
            result = _parse_structured(response, schema)
            if result is not None:
                return result
            if attempt < attempts:
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
        ctx.outcomes.append(
            ItemOutcome(
                sequence,
                "failed",
                error_type="InvalidOutput",
                error="Structured output attempts exhausted",
            )
        )
        return None

    try:
        if isolation == "worktree":
            async with worktree_session(label=name, run_id=ctx.run_id) as handle:
                result = await _execute_agent()
            if handle.dirty:
                log(f"worktree kept (dirty): {handle.path}")
        else:
            result = await _execute_agent()
    except BaseException:
        entry = serialize_agent_result(None, schema)
        entry.result_kind = "error"
        entry.sequence = sequence
        entry.cache_key = cache_key
        entry.prompt = prompt
        entry.usage = step_usage.usage()
        ctx.journal.append(entry)
        ctx.journal.persist(ctx.journal_path)
        raise

    entry = serialize_agent_result(result, schema)
    entry.sequence = sequence
    entry.cache_key = cache_key
    entry.prompt = prompt
    entry.usage = step_usage.usage()
    ctx.journal.append(entry)
    _store_step_output(ctx, label, result)
    ctx.journal.persist(ctx.journal_path)
    return result


def _store_step_output(ctx: _RunCtx, label: str | None, result: Any) -> None:
    """Restore the same visibility for both live and cached results."""
    if label is not None and result is not None:
        ctx.step_outputs[label] = (
            result.model_dump_json() if isinstance(result, BaseModel) else str(result)
        )


def _parse_structured(response: str, schema: type[BaseModel]) -> BaseModel | None:
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


def _batch_result(outcomes: list[ItemOutcome], errors: str) -> list[Any]:
    ctx = _ctx()
    ctx.outcomes.extend(outcomes)
    if errors == "raise" and any(o.status == "failed" for o in outcomes):
        raise BatchFailed(outcomes)
    if errors == "collect":
        return outcomes
    return [o.value if o.status == "completed" else None for o in outcomes]


def _validate_batch(count: int, errors: str) -> None:
    _ctx()
    if errors not in ("raise", "collect", "legacy"):
        raise ValueError("errors must be 'raise', 'collect' or explicit 'legacy'")
    if count > _MAX_ITEM_CAP:
        raise ValueError(f"batch accepts at most {_MAX_ITEM_CAP} items, got {count}")


async def _gather_settled(*coroutines):
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # A cancelled child must not outlive the run and keep mutating its journal.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def parallel(
    thunks: Sequence[Callable[[], Awaitable[Any]]], *, errors: str = "raise"
) -> list[Any]:
    """Wait for every sibling, then raise BatchFailed with all outcomes on failure.

    errors='collect' returns ItemOutcome objects. Explicit errors='legacy' returns
    values/None, while Workflow.report still records a partial terminal state.
    Cancellation propagates instead of being converted to a successful value.
    """
    _validate_batch(len(thunks), errors)

    async def run(index, thunk):
        try:
            return ItemOutcome(index, "completed", value=await thunk())
        except Exception as error:  # noqa: BLE001 — retain all batch failure evidence
            return ItemOutcome(
                index,
                "failed",
                error_type=type(error).__name__,
                error=str(error),
                traceback=traceback.format_exc(),
            )

    return _batch_result(
        await _gather_settled(*(run(i, t) for i, t in enumerate(thunks))), errors
    )


async def pipeline(
    items: Sequence[Any],
    *stages: Callable[[Any, Any, int], Awaitable[Any]],
    errors: str = "raise",
) -> list[Any]:
    """Pipeline with structured failures including last value and completed stages."""
    _validate_batch(len(items), errors)

    async def chain(item, index):
        prev, completed = item, 0
        try:
            for stage in stages:
                prev = await stage(prev, item, index)
                completed += 1
            return ItemOutcome(
                index, "completed", value=prev, completed_stages=completed
            )
        except Exception as error:  # noqa: BLE001 — retain all batch failure evidence
            return ItemOutcome(
                index,
                "failed",
                value=prev,
                error_type=type(error).__name__,
                error=str(error),
                traceback=traceback.format_exc(),
                completed_stages=completed,
            )

    return _batch_result(
        await _gather_settled(*(chain(it, i) for i, it in enumerate(items))), errors
    )


async def workflow(
    script_or_name: Callable[[], Awaitable[Any]] | str,
    *,
    args: Any = None,
) -> Any:
    """Run a workflow script, joining the parent run when already inside one.

    ``script_or_name`` may be a coroutine function or a registered workflow name.
    Standalone opens a fresh run; inside an outer script at depth 0 joins that
    run's budget and concurrency cap. Nesting is limited to one level.
    """
    if isinstance(script_or_name, str):
        script = _get_registered_workflow(script_or_name)
        registry_name = script_or_name
    else:
        script = script_or_name
        registry_name = None

    ctx = _current.get()
    if ctx is None:
        return await Workflow(script, args=args, registry_name=registry_name).run()
    if ctx.depth >= 1:
        raise RuntimeError(
            "workflow() nesting is limited to one level — workflow() cannot "
            "be called inside a child workflow."
        )
    prev_args = ctx.args
    prev_registry = ctx.registry_name
    ctx.depth = 1
    ctx.args = args
    ctx.registry_name = registry_name
    try:
        return await script()
    finally:
        ctx.depth = 0
        ctx.args = prev_args
        ctx.registry_name = prev_registry


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
        meta: dict[str, Any] | None = None,
        resume_run_id: str | None = None,
        journal_dir: str | Path | None = None,
        registry_name: str | None = None,
        resume_version: str | None = None,
        model_turn_limit: int | None = None,
    ):
        if model_turn_limit is not None and model_turn_limit < 1:
            raise ValueError("model_turn_limit must be positive")
        self._model_turn_limit = model_turn_limit
        self.report: WorkflowReport | None = None
        self._resume_version = resume_version
        self.script = script
        self._args = args
        self._budget_total = budget_total
        self._budget_unit = budget_unit
        self._concurrency = concurrency
        self._meta = meta
        self._resume_run_id = resume_run_id
        self._journal_dir = Path(journal_dir) if journal_dir else default_journal_dir()
        self._registry_name = registry_name

    async def run(self) -> Any:
        if self._resume_run_id:
            if Path(
                self._resume_run_id
            ).name != self._resume_run_id or self._resume_run_id in (".", ".."):
                raise ValueError("run_id must be a single directory name")
            with journal_lock(self._journal_dir / self._resume_run_id):
                return await self._run()
        return await self._run()

    async def _run(self) -> Any:
        if self._meta is not None:
            _validate_meta(self._meta)
        cap = (
            self._concurrency
            or int(os.environ.get("DIALECTICA_WORKFLOW_CONCURRENCY", "0") or "0")
            or _DEFAULT_CONCURRENCY
        )
        journal, journal_path = RunJournal.create(
            script=self.script,
            args=self._args,
            registry_name=self._registry_name,
            resume_run_id=self._resume_run_id,
            journal_dir=self._journal_dir,
            resume_version=self._resume_version,
        )
        ctx = _RunCtx(
            budget=Budget(
                total=self._budget_total,
                unit=self._budget_unit,
                model_turn_limit=self._model_turn_limit,
            ),
            run_id=journal.run_id,
            journal=journal,
            journal_path=journal_path,
            concurrency=cap,
            semaphore=asyncio.Semaphore(cap),
            args=self._args,
            registry_name=self._registry_name,
            meta=self._meta,
        )
        lock = journal_lock(journal_path.parent) if not self._resume_run_id else None
        if lock is not None:
            lock.__enter__()
        self.report = WorkflowReport(journal.run_id)
        token = _current.set(ctx)
        guard_token = agent_runtime.model_call_guard.set(ctx.budget._admit_model_turn)
        try:
            result = await self.script()
            _check_meta_phases(ctx)
            self.report.value = result
            self.report.status = (
                "partial"
                if any(o.status == "failed" for o in ctx.outcomes)
                else "completed"
            )
            return result
        except BaseException as error:
            self.report.status = (
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            )
            self.report.error = f"{type(error).__name__}: {error}"
            raise
        finally:
            ctx.journal.terminal_state = self.report.status
            self.report.outcomes = list(ctx.outcomes)
            self.report.usage = ctx.budget.usage()
            self.report.agent_steps = ctx.budget.spent_calls()
            try:
                ctx.journal.persist(ctx.journal_path)
            finally:
                _current.reset(token)
                agent_runtime.model_call_guard.reset(guard_token)
                if lock is not None:
                    lock.__exit__(None, None, None)


__all__ = [
    "BatchFailed",
    "Budget",
    "BudgetExhausted",
    "ItemOutcome",
    "ResumeUnsafeError",
    "Workflow",
    "WorkflowAgentCapExceeded",
    "WorkflowMetaError",
    "WorkflowReport",
    "WorkflowWorktreeError",
    "agent",
    "args",
    "budget",
    "in_workflow",
    "list_workflows",
    "log",
    "parallel",
    "phase",
    "pipeline",
    "register_workflow",
    "run_id",
    "workflow",
    "worktree_path",
]
