"""Iterative self-refinement with configurable selection and early convergence.

Lineage: Madaan et al. (2023) "Self-Refine: Iterative Refinement with Self-Feedback".
Dialectica finding (2026-10-04 development selection study):
- Unguided self-refinement (returning the final attempt, ``policy="last"``) ties
  a single call on self-contained tasks (2/16 vs 2/16, 12.5% on portfolio dev).
- Intermediate trajectory coverage is substantially higher (9/16, 56.25%), but
  the unguided model drifts away from optimal solutions in 77.8% of cases.
- Oracle-free candidate checkers or trajectory consensus (``policy="plurality"``)
  rescue those lost answers without consulting the hidden optimum.
- Consecutive confirmation (``policy="convergence"``) enables early stopping,
  averaging ~3 steps instead of 8 while preserving or lifting final pass rates.

Built on the ``Workflow`` kernel: each refinement step is one ``wf.agent()`` call.
"""

from collections.abc import Callable
from typing import Any, Literal

from dialectica import workflow as wf
from dialectica.json_repair import strip_code_fence

Policy = Literal["last", "first", "convergence", "plurality"]


class SelfRefineEngine:
    """Iterative self-refine loop over a single model or rotating roster."""

    def __init__(
        self,
        problem: str,
        max_steps: int = 4,
        models: list[str] | None = None,
        policy: Policy = "last",
        selector: Callable[[list[str]], int] | None = None,
        equality_fn: Callable[[str, str], bool] | None = None,
    ):
        self.problem = problem
        self.max_steps = max(1, max_steps)
        self.models = models or [None]
        self.policy = policy
        self.selector = selector
        self.equality_fn = equality_fn or self._default_equality

    @staticmethod
    def _default_equality(a: str, b: str) -> bool:
        """Strip whitespace and code fences for string comparison."""
        return strip_code_fence(a).strip() == strip_code_fence(b).strip()

    def _select_index(self, answers: list[str]) -> int:
        if self.selector is not None:
            return self.selector(answers)
        if self.policy == "first" or not answers:
            return 0
        if self.policy == "last":
            return len(answers) - 1
        if self.policy == "plurality":
            counts: dict[str, int] = {}
            latest: dict[str, int] = {}
            for i, ans in enumerate(answers):
                clean = strip_code_fence(ans).strip()
                counts[clean] = counts.get(clean, 0) + 1
                latest[clean] = i
            best_count = max(counts.values())
            candidates = [latest[k] for k, v in counts.items() if v == best_count]
            return max(candidates)
        # Fallback to last
        return len(answers) - 1

    async def run(self) -> dict[str, Any]:
        async def script() -> dict[str, Any]:
            answers: list[str] = []
            converged = False

            for step in range(self.max_steps):
                context = ""
                if answers:
                    context = (
                        f"\nPREVIOUS ANSWER:\n{answers[-1]}\n"
                        "Independently check every constraint, logic step, and calculation. "
                        "Correct any flaw found and retain a correct answer."
                    )
                model = self.models[step % len(self.models)]
                answer = await wf.agent(
                    self.problem
                    + context
                    + "\nSolve carefully and return your complete answer in the required format.",
                    model=model,
                    label=f"self_refine-{step}",
                    sees=[],
                )
                answers.append(answer)

                if (
                    self.policy == "convergence"
                    and len(answers) >= 2
                    and self.equality_fn(answers[-1], answers[-2])
                ):
                    converged = True
                    break

            if self.policy == "convergence":
                selected_idx = len(answers) - 1
            else:
                selected_idx = self._select_index(answers)

            return {
                "final_answer": answers[selected_idx],
                "selected_index": selected_idx,
                "converged": converged,
                "steps": len(answers),
                "trajectory": answers,
                "policy": self.policy,
            }

        return await wf.workflow(script)


def create_self_refine_engine(
    problem: str,
    max_steps: int = 4,
    models: list[str] | None = None,
    policy: Policy = "last",
    selector: Callable[[list[str]], int] | None = None,
    equality_fn: Callable[[str, str], bool] | None = None,
) -> SelfRefineEngine:
    """Create an iterative self-refine engine over the Workflow kernel.

    Args:
        problem: The problem statement or prompt.
        max_steps: Maximum refinement iterations.
        models: Optional model or roster of models to cycle through.
        policy: "last" (default standard self-refine), "convergence" (stops early
            when two consecutive iterations match), "plurality" (mode of trajectory),
            or "first" (single attempt).
        selector: Optional custom callable taking list[str] of answers and returning
            the selected index (e.g. an external constraint checker or verifier).
        equality_fn: Equality function for convergence detection.
    """
    return SelfRefineEngine(
        problem=problem,
        max_steps=max_steps,
        models=models,
        policy=policy,
        selector=selector,
        equality_fn=equality_fn,
    )
