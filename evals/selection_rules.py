"""Deployable final-selection rules over a saved self-refinement trajectory.

Held-out diagnostics showed self-refinement often holds a correct intermediate
answer that last-answer selection discards. These rules choose a final answer
from the same saved candidates **without** the optimality oracle:

- ``first`` / ``last``: the single-call answer and today's self-refine output.
- ``plurality``: most frequent parsed prediction, ties to the latest occurrence.
- ``convergence``: first answer confirmed by its immediate successor (a rule
  that could also stop refinement early); falls back to the last parseable one.
- ``checker``: a task-statement check (feasibility under capacity/exclusions,
  then highest total reward). Uses only data printed in the prompt, never the
  optimum, but is task-specific — it stands in for any cheap candidate checker.

The hidden optimum stays in the evaluator; ``oracle`` coverage is computed by
the study runner as an upper bound, not as a selector.
"""

from collections.abc import Callable

from evals.meta_ablation import prediction_key
from evals.research_tasks import PortfolioTask

RULES = ("first", "last", "plurality", "convergence", "checker")


def _keys(answers: list[str], family: str) -> list[tuple[int, ...] | None]:
    keys: list[tuple[int, ...] | None] = []
    for answer in answers:
        try:
            keys.append(prediction_key(answer, family))
        except ValueError:
            keys.append(None)
    return keys


def plurality_index(answers: list[str], family: str) -> int | None:
    counts: dict[tuple[int, ...], int] = {}
    latest: dict[tuple[int, ...], int] = {}
    for index, key in enumerate(_keys(answers, family)):
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
        latest[key] = index
    if not counts:
        return None
    best = max(counts.values())
    return max(latest[key] for key, count in counts.items() if count == best)


def convergence_index(answers: list[str], family: str) -> int | None:
    keys = _keys(answers, family)
    for index in range(1, len(keys)):
        if keys[index] is not None and keys[index] == keys[index - 1]:
            return index
    parsed = [index for index, key in enumerate(keys) if key is not None]
    return parsed[-1] if parsed else None


def checker_index(answers: list[str], task: PortfolioTask) -> int | None:
    best: tuple[int, int] | None = None  # (reward, index)
    for index, key in enumerate(_keys(answers, "portfolio")):
        if key is None or len(set(key)) != len(key):
            continue
        if any(not 0 <= item < len(task.rewards) for item in key):
            continue
        if sum(task.weights[item] for item in key) > task.capacity:
            continue
        chosen = set(key)
        if any(a in chosen and b in chosen for a, b in task.exclusions):
            continue
        reward = sum(task.rewards[item] for item in key)
        if best is None or reward >= best[0]:
            best = (reward, index)
    return None if best is None else best[1]


def selector_indices(
    answers: list[str], task: PortfolioTask, family: str = "portfolio"
) -> dict[str, int | None]:
    if not answers:
        raise ValueError("at least one candidate answer is required")
    rules: dict[str, Callable[[], int | None]] = {
        "first": lambda: 0,
        "last": lambda: len(answers) - 1,
        "plurality": lambda: plurality_index(answers, family),
        "convergence": lambda: convergence_index(answers, family),
        "checker": lambda: checker_index(answers, task),
    }
    return {name: rule() for name, rule in rules.items()}
