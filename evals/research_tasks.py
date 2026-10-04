"""Seeded verifier-backed tasks with separate development and held-out inputs.

This is a controlled task family, not a reproduction of a published benchmark.
The optimum is never placed in the task prompt. Feasible but suboptimal answers
fail the hidden evaluation, avoiding a format-only success criterion.
"""

import json
import random
from dataclasses import dataclass
from functools import cached_property

from dialectica.json_repair import strip_code_fence


@dataclass(frozen=True)
class PortfolioTask:
    task_id: str
    rewards: tuple[int, ...]
    weights: tuple[int, ...]
    capacity: int
    exclusions: tuple[tuple[int, int], ...]

    @property
    def statement(self) -> str:
        items = "\n".join(
            f"{i}: reward={reward}, cost={weight}"
            for i, (reward, weight) in enumerate(
                zip(self.rewards, self.weights, strict=True)
            )
        )
        return (
            "Select a globally optimal subset of projects maximizing total reward. "
            "Each project can be selected at most once. Total cost must not exceed "
            f"{self.capacity}. Mutually exclusive pairs (never select both): {self.exclusions}.\n"
            f"Projects (zero-based IDs):\n{items}\n"
            'Return one JSON object only: {"selected": [project IDs]}. '
            "A feasible but suboptimal subset is incorrect. Any globally optimal subset is accepted."
        )

    @cached_property
    def _solution(self) -> tuple[int, tuple[int, ...]]:
        best_value = -1
        best_selection: tuple[int, ...] = ()
        for mask in range(1 << len(self.rewards)):
            selected = tuple(i for i in range(len(self.rewards)) if mask & (1 << i))
            if sum(self.weights[i] for i in selected) > self.capacity:
                continue
            if any(mask & (1 << a) and mask & (1 << b) for a, b in self.exclusions):
                continue
            value = sum(self.rewards[i] for i in selected)
            if value > best_value:
                best_value, best_selection = value, selected
        return best_value, best_selection

    def optimal_value(self) -> int:
        return self._solution[0]

    def optimal_selection(self) -> tuple[int, ...]:
        return self._solution[1]

    def verify(self, answer: str) -> tuple[bool, str]:
        try:
            payload = json.loads(answer)
        except (ValueError, TypeError):
            return False, "Return a valid JSON object with selected project IDs."
        selected = payload.get("selected") if isinstance(payload, dict) else None
        if not isinstance(selected, list) or any(
            type(i) is not int or i < 0 or i >= len(self.rewards) for i in selected
        ):
            return False, "selected must be a list of valid zero-based integer IDs."
        if len(set(selected)) != len(selected):
            return False, "Project IDs cannot be repeated."
        if sum(self.weights[i] for i in selected) > self.capacity:
            return False, "The total project cost exceeds capacity."
        if any(a in selected and b in selected for a, b in self.exclusions):
            return False, "A mutually exclusive pair was selected."
        if sum(self.rewards[i] for i in selected) != self.optimal_value():
            return False, "The subset is feasible but not globally optimal."
        return True, ""

    def verify_content(self, answer: str) -> tuple[bool, str]:
        """Ignore a whole-answer Markdown fence, without repairing task content."""
        return self.verify(strip_code_fence(answer))


def make_portfolio_tasks(
    split: str, count: int = 16, size: int = 14
) -> list[PortfolioTask]:
    if split not in {"dev", "heldout"}:
        raise ValueError("split must be dev or heldout")
    if count < 1 or not 4 <= size <= 18:
        raise ValueError("count must be positive and size must be between 4 and 18")
    rng = random.Random(31003 if split == "dev" else 71004)
    tasks = []
    for index in range(count):
        rewards = tuple(rng.randint(9, 89) for _ in range(size))
        weights = tuple(rng.randint(4, 29) for _ in range(size))
        pairs = set()
        while len(pairs) < size // 2:
            pairs.add(tuple(sorted(rng.sample(range(size), 2))))
        tasks.append(
            PortfolioTask(
                f"portfolio-{split}-{index:03}",
                rewards,
                weights,
                sum(weights) * 2 // 5,
                tuple(sorted(pairs)),
            )
        )
    return tasks


@dataclass(frozen=True)
class StateTask:
    """A controlled long-horizon task, not a published benchmark reproduction."""

    task_id: str
    initial: tuple[int, ...]
    operations: tuple[tuple[str, int, int, int], ...]

    @property
    def statement(self) -> str:
        return (
            f"Track registers 0..{len(self.initial) - 1}, initially {self.initial}. "
            "Execute the numbered operations in order. After each operation reduce "
            "every register modulo 97 to 0..96. add(i,j,n) adds n to register i "
            "(j is ignored). move(i,j,n) simultaneously subtracts n from i and adds "
            "n to j; insufficient balance is allowed. swap(i,j,n) swaps i and j "
            "(n is ignored). if_add(i,j,n) compares the pre-operation values: "
            "if register i > register j add n to i, otherwise add n to j.\n"
            + "\n".join(
                f"{step}: {kind}({i},{j},{n})"
                for step, (kind, i, j, n) in enumerate(self.operations, 1)
            )
            + '\nReturn only {"state": [final register values in register order]}.'
        )

    def final_state(self) -> tuple[int, ...]:
        values = list(self.initial)
        for kind, i, j, n in self.operations:
            if kind == "add":
                values[i] += n
            elif kind == "move":
                values[i] -= n
                values[j] += n
            elif kind == "swap":
                values[i], values[j] = values[j], values[i]
            elif kind == "if_add":
                values[i if values[i] > values[j] else j] += n
            else:
                raise ValueError("unknown state operation")
            values = [value % 97 for value in values]
        return tuple(values)

    def verify(self, answer: str) -> tuple[bool, str]:
        try:
            payload = json.loads(answer)
        except (ValueError, TypeError):
            return False, "Return a JSON state object."
        values = payload.get("state") if isinstance(payload, dict) else None
        if (
            not isinstance(values, list)
            or len(values) != len(self.initial)
            or any(type(value) is not int or not 0 <= value < 97 for value in values)
        ):
            return False, "state must contain one integer in 0..96 per register."
        if tuple(values) != self.final_state():
            return False, "The final register state is incorrect."
        return True, ""

    def verify_content(self, answer: str) -> tuple[bool, str]:
        return self.verify(strip_code_fence(answer))


def make_state_tasks(split: str, count: int = 16, steps: int = 24) -> list[StateTask]:
    if split not in {"dev", "heldout"} or count < 1 or not 1 <= steps <= 100:
        raise ValueError("valid split, positive count and 1..100 steps required")
    rng = random.Random(51004 if split == "dev" else 91004)
    tasks = []
    for index in range(count):
        initial = tuple(rng.randrange(97) for _ in range(6))
        operations = []
        for _ in range(steps):
            i, j = rng.sample(range(6), 2)
            operations.append(
                (
                    rng.choice(["add", "move", "swap", "if_add"]),
                    i,
                    j,
                    rng.randint(1, 40),
                )
            )
        tasks.append(StateTask(f"state-{split}-{index:03}", initial, tuple(operations)))
    return tasks
