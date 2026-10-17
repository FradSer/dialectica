"""Execution-guided repair using an injected objective verifier.

Generate -> run the verifier -> feed concrete failure feedback back -> regenerate,
until verification passes or attempts run out. Historical comparisons found
cost savings from stopping on success at matched best-of-K reliability; those
observations are task/model-specific, not universal superiority claims.

The verifier is injected as a plain ``Callable[[answer], (passed, feedback)]``,
so the engine is task-agnostic: it works for ANY objective checker — unit tests,
a schema validator, a linter, a SQL ``EXPLAIN``, assertion-checked business
logic — not just code. The consuming app supplies "how to check it"; the edge
over an unchecked attempt is access to the verifier's concrete feedback.
The reliability of that feedback depends on the supplied checker; an LLM
self-score is not automatically objective ground truth.

Built on ``workflow.py``'s shared execution kernel: each attempt is one
``wf.agent(model=..., label=...)`` call inside a private ``Workflow`` script,
so repair is "just" a bounded retry loop over the same primitives every other
workflow uses — no bespoke ``LlmAgent`` construction of its own. When
``create_repair_engine(...).run()`` is called from inside an outer ``Workflow``
script it joins that run's context, so its attempts are charged to the outer
``budget_total`` and share the outer concurrency cap (the child-workflow rule);
standalone it opens its own fresh ``Workflow`` context. A joined run can
therefore raise ``BudgetExhausted`` mid-loop when the outer budget runs out —
the engine retains completed verifier evidence in ``last_history``; standalone runs are unbudgeted and never raise it.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from . import workflow as wf

logger = logging.getLogger(__name__)


# Given the model's raw answer, return (passed, feedback). ``feedback`` is the
# concrete failure to repair against (assertion errors, wrong output, a stack
# trace) — empty when it passed.
@dataclass(frozen=True)
class VerificationResult:
    """Host evidence: pass/fail/indeterminate; only explicit pass accepts work."""

    status: Literal["pass", "fail", "indeterminate"]
    feedback: str = ""
    evidence: str = ""

    def __post_init__(self):
        if self.status not in ("pass", "fail", "indeterminate"):
            raise ValueError("invalid verification status")


VerifierValue = VerificationResult | tuple[bool, str]
Verifier = Callable[[str], VerifierValue | Awaitable[VerifierValue]]


async def verify(verifier: Verifier, answer: str) -> VerificationResult:
    """Legacy bool tuples are supported; checker errors are indeterminate."""
    try:
        value = verifier(answer)
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, VerificationResult):
            return value
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and type(value[0]) is bool
            and isinstance(value[1], str)
        ):
            return VerificationResult("pass" if value[0] else "fail", value[1])
        return VerificationResult("indeterminate", "Invalid verifier return value")
    except Exception as error:  # noqa: BLE001 — checker failure is indeterminate
        return VerificationResult("indeterminate", f"{type(error).__name__}: {error}")


SOLVE_PROMPT = (
    "Solve the following problem. Reason it through, then provide your "
    "COMPLETE solution.{format_hint}\n\n{problem}"
)

REPAIR_PROMPT = (
    "Your solution did NOT pass verification. Below is every previous attempt and the "
    "EXACT failure each produced — use the full history so you do not repeat a fix "
    "that already failed, and do not restart from scratch unless the whole approach "
    "is wrong.\n\n"
    "**Problem:**\n"
    "{problem}\n\n"
    "**Previous attempts and their verifier failures (ground truth):**\n"
    "{history_block}\n\n"
    "Diagnose what specifically failed — and, if earlier fixes did not work, why — "
    "then provide your COMPLETE corrected solution.{format_hint}"
)


class IterativeRepairEngine:
    """Generate -> verify -> repair-against-the-failure, until pass or out of tries.

    Accepts a roster of model configs (``"provider:model_name"`` strings, or
    ``None`` entries to inherit the session default). With more than one
    model, each failed attempt rotates to the next model round-robin, cycling
    back when the roster is exhausted. A one-element roster is byte-identical
    to a single model.
    """

    def __init__(
        self,
        problem: str,
        models: list[str | None],
        verifier: Verifier,
        max_attempts: int = 3,
        solution_format: str = "",
        labels: list[str] | None = None,
    ):
        self.last_history: list[dict[str, Any]] = []
        self.problem = problem
        if not models:
            raise ValueError("models must not be empty")
        self._models = models
        # The label recorded in history per attempt — the raw ``provider:model``
        # config for a roster, else a placeholder for the single-model default.
        self._labels: list[str] = labels or [m or "default" for m in models]
        self.verifier = verifier
        self.max_attempts = max(1, max_attempts)
        # Optional domain output-format hint (e.g. "Return a single ```python
        # code block." or "Return only the JSON object."); keeps the engine
        # general while letting callers pin the format their verifier parses.
        self._format_hint = f" {solution_format}" if solution_format else ""

    @staticmethod
    def _history_block(failed: list[tuple[str, str]]) -> str:
        """Render every prior failed attempt + its verifier failure (bounded)."""
        return "\n\n".join(
            f"--- Attempt {i} ---\n{ans[:1500]}\n[Verifier failure]: {fb[:500]}"
            for i, (ans, fb) in enumerate(failed, 1)
        )

    async def run(self) -> dict[str, Any]:
        """Solve with verifier-in-the-loop; return the final answer + trace.

        Each history entry carries ``{"attempt": n, "passed": bool, "model": label}``
        where ``label`` is the roster member (the raw ``provider:model`` config for
        a roster, else the single-model placeholder) that produced the attempt.
        """

        self.last_history = []

        async def script() -> dict[str, Any]:
            idx = 0
            answer = (
                await wf.agent(
                    SOLVE_PROMPT.format(
                        problem=self.problem, format_hint=self._format_hint
                    ),
                    model=self._models[idx],
                    label=self._labels[idx],
                )
            ).strip()
            verdict = await verify(self.verifier, answer)
            passed, feedback = verdict.status == "pass", verdict.feedback
            history: list[dict[str, Any]] = [
                {
                    "attempt": 1,
                    "passed": passed,
                    "model": self._labels[idx],
                    "status": verdict.status,
                    "feedback": feedback,
                    "evidence": verdict.evidence,
                }
            ]
            self.last_history = list(history)
            logger.info("Attempt 1: passed=%s (model=%s)", passed, self._labels[idx])

            failed: list[tuple[str, str]] = []
            attempt = 1
            while verdict.status == "fail" and attempt < self.max_attempts:
                failed.append((answer, feedback))
                attempt += 1
                idx = (attempt - 1) % len(self._models)
                answer = (
                    await wf.agent(
                        REPAIR_PROMPT.format(
                            problem=self.problem,
                            history_block=self._history_block(failed),
                            format_hint=self._format_hint,
                        ),
                        model=self._models[idx],
                        label=self._labels[idx],
                    )
                ).strip()
                verdict = await verify(self.verifier, answer)
                passed, feedback = verdict.status == "pass", verdict.feedback
                history.append(
                    {
                        "attempt": attempt,
                        "passed": passed,
                        "model": self._labels[idx],
                        "status": verdict.status,
                        "feedback": feedback,
                        "evidence": verdict.evidence,
                    }
                )
                self.last_history = list(history)
                logger.info(
                    "Repair attempt %d: passed=%s (model=%s)",
                    attempt,
                    passed,
                    self._labels[idx],
                )

            return {
                "final_answer": answer,
                "passed": passed,
                "status": verdict.status,
                "verification": verdict,
                "attempts": attempt,
                "history": history,
            }

        return await wf.workflow(script)


def create_repair_engine(
    problem: str,
    verifier: Verifier,
    max_attempts: int = 3,
    model_config: str | None = None,
    solution_format: str = "",
    models: list[str] | None = None,
) -> IterativeRepairEngine:
    """Wire an IterativeRepairEngine with one model config or a roster.

    ``verifier(raw_answer) -> (passed, feedback)`` is the objective checker; the
    engine is task-agnostic and only reacts to what it returns. ``solution_format``
    optionally pins the output shape the verifier expects (e.g. a ```python code
    block, or "only the JSON object").

    Pass ``models`` to enable round-robin rotation over a roster of model configs
    (``"provider:model_name"`` strings). Each failed attempt rotates to the next
    model; the cycle wraps back when all members have been tried. This is
    deeper-only rotation with a boolean verifier — see the ensemble pattern
    (``examples/patterns/ensemble_pattern.py``) for wider+deeper sampling with a
    float scorer.

    ``model_config`` and ``models`` are mutually exclusive; passing both raises
    ``ValueError``.
    """
    if model_config is not None and models is not None:
        raise ValueError(
            "conflicting configuration: pass either model_config (single model) "
            "or models (roster), not both"
        )
    if models is not None:
        resolved_models: list[str | None] = list(models)
        labels: list[str] | None = list(models)
    else:
        resolved_models = [model_config]
        labels = None
    return IterativeRepairEngine(
        problem, resolved_models, verifier, max_attempts, solution_format, labels
    )
