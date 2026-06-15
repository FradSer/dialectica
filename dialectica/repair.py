"""Execution-guided repair — the one engine that structurally beats a single call.

A single forward pass writes a solution once and cannot learn whether it was
correct. On verifiable tasks (code with tests, or anything with an objective
checker) this engine closes that loop: generate -> run the verifier -> feed the
CONCRETE failure back -> regenerate, until the verifier passes or attempts run
out.

The edge over one shot is ground-truth feedback the single pass never sees — NOT
an LLM self-evaluation (same model, no ground truth), which the evals showed
adds nothing on its own. The verifier is injected as a plain callable, so the
engine stays task-agnostic: the consuming app supplies "run the tests".
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

SOLVE_PROMPT = """Solve the following problem. Reason it through, then give the COMPLETE implementation in a single ```python code block.

{problem}"""

REPAIR_PROMPT = """Your previous solution did NOT pass the tests. Use the concrete failure below to fix it — keep what works; do not restart from scratch unless the whole approach is wrong.

**Problem:**
{problem}

**Your previous solution:**
{previous}

**Verifier feedback (ground truth — the actual failure):**
{feedback}

Diagnose exactly what failed, then give the COMPLETE corrected implementation in a single ```python code block."""


class IterativeRepairEngine:
    """Generate -> verify -> repair-against-the-failure, until pass or out of tries."""

    def __init__(
        self,
        problem: str,
        generator,
        verifier: Verifier,
        max_attempts: int = 3,
    ):
        self.problem = problem
        self.generator = generator
        self.verifier = verifier
        self.max_attempts = max(1, max_attempts)

    async def run(self) -> dict[str, Any]:
        """Solve with verifier-in-the-loop; return the final answer + trace."""
        answer = (
            await agent_runtime.run_agent(
                self.generator, SOLVE_PROMPT.format(problem=self.problem)
            )
        ).strip()
        passed, feedback = self.verifier(answer)
        history: list[dict[str, Any]] = [{"attempt": 1, "passed": passed}]
        logger.info("Attempt 1: passed=%s", passed)

        attempt = 1
        while not passed and attempt < self.max_attempts:
            attempt += 1
            answer = (
                await agent_runtime.run_agent(
                    self.generator,
                    REPAIR_PROMPT.format(
                        problem=self.problem, previous=answer, feedback=feedback
                    ),
                )
            ).strip()
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
) -> IterativeRepairEngine:
    """Wire an IterativeRepairEngine with a default Generator agent.

    ``verifier(raw_answer) -> (passed, feedback)`` is the objective checker; the
    engine is task-agnostic and only reacts to what it returns.
    """
    generator = create_agent(
        role="Generator",
        role_name="Solver",
        model_config=model_config or get_model_config("GENERATOR"),
    )
    return IterativeRepairEngine(problem, generator, verifier, max_attempts)
