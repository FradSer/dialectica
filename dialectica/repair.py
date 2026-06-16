"""Execution-guided repair — Dialectica's core engine, the one that structurally
beats a single strong-model call.

Controlled evals settled it: pure-LLM reasoning scaffolds (ToT, GAN, the
dialectic) only rearrange the model's own thinking on the same context — they
add no information, so they tie a prompt-matched single call. A scaffold beats
one pass only by doing something one pass cannot: act on objective ground truth
and react. This engine is that loop — generate -> run the verifier -> feed the
CONCRETE failure back -> regenerate — until the verifier passes or attempts run
out.

The verifier is injected as a plain ``Callable[[answer], (passed, feedback)]``,
so the engine is task-agnostic: it works for ANY objective checker — unit tests,
a schema validator, a linter, a SQL ``EXPLAIN``, assertion-checked business
logic — not just code. The consuming app supplies "how to check it"; the edge
over one shot is the ground-truth feedback the single pass never sees (not an
LLM self-score on the same model, which the evals showed adds nothing).
"""

import logging
from collections.abc import Callable
from typing import Any, Optional

from . import agent_runtime
from .agent_factory import create_agent
from .llm_config import get_model_config

logger = logging.getLogger(__name__)

# Given the model's raw answer, return (passed, feedback). ``feedback`` is the
# concrete failure to repair against (assertion errors, wrong output, a stack
# trace) — empty when it passed.
Verifier = Callable[[str], tuple[bool, str]]

SOLVE_PROMPT = """Solve the following problem. Reason it through, then provide your COMPLETE solution.{format_hint}

{problem}"""

REPAIR_PROMPT = """Your solution did NOT pass verification. Below is every previous attempt and the EXACT failure each produced — use the full history so you do not repeat a fix that already failed, and do not restart from scratch unless the whole approach is wrong.

**Problem:**
{problem}

**Previous attempts and their verifier failures (ground truth):**
{history_block}

Diagnose what specifically failed — and, if earlier fixes did not work, why — then provide your COMPLETE corrected solution.{format_hint}"""


class IterativeRepairEngine:
    """Generate -> verify -> repair-against-the-failure, until pass or out of tries."""

    def __init__(
        self,
        problem: str,
        generator,
        verifier: Verifier,
        max_attempts: int = 3,
        solution_format: str = "",
    ):
        self.problem = problem
        self.generator = generator
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
        """Solve with verifier-in-the-loop; return the final answer + trace."""
        answer = (
            await agent_runtime.run_agent(
                self.generator,
                SOLVE_PROMPT.format(
                    problem=self.problem, format_hint=self._format_hint
                ),
            )
        ).strip()
        passed, feedback = self.verifier(answer)
        history: list[dict[str, Any]] = [{"attempt": 1, "passed": passed}]
        logger.info("Attempt 1: passed=%s", passed)

        failed: list[tuple[str, str]] = []
        seen: set[str] = {answer}
        attempt = 1
        while not passed and attempt < self.max_attempts:
            failed.append((answer, feedback))
            attempt += 1
            answer = (
                await agent_runtime.run_agent(
                    self.generator,
                    REPAIR_PROMPT.format(
                        problem=self.problem,
                        history_block=self._history_block(failed),
                        format_hint=self._format_hint,
                    ),
                )
            ).strip()
            # No-progress stop: a repeated solution yields a repeated verdict, so
            # re-verifying it would burn a call for nothing.
            if answer in seen:
                logger.info(
                    "Repair attempt %d reproduced a prior solution; stopping early.",
                    attempt,
                )
                history.append(
                    {"attempt": attempt, "passed": False, "note": "no-progress"}
                )
                passed = False
                break
            seen.add(answer)
            passed, feedback = self.verifier(answer)
            history.append({"attempt": attempt, "passed": passed})
            logger.info("Repair attempt %d: passed=%s", attempt, passed)

        return {
            "final_answer": answer,
            "passed": passed,
            "attempts": attempt,
            "history": history,
        }


def create_repair_engine(
    problem: str,
    verifier: Verifier,
    max_attempts: int = 3,
    model_config: Optional[str] = None,
    solution_format: str = "",
) -> IterativeRepairEngine:
    """Wire an IterativeRepairEngine with a default Generator agent.

    ``verifier(raw_answer) -> (passed, feedback)`` is the objective checker; the
    engine is task-agnostic and only reacts to what it returns. ``solution_format``
    optionally pins the output shape the verifier expects (e.g. a ```python code
    block, or "only the JSON object").
    """
    generator = create_agent(
        role="Generator",
        role_name="Solver",
        model_config=model_config or get_model_config("GENERATOR"),
    )
    return IterativeRepairEngine(
        problem, generator, verifier, max_attempts, solution_format
    )
