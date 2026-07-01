"""Deterministic mock helpers shared across the mocked tests."""

import collections
from collections.abc import Callable
from typing import Any

#: Sentinel value for ``make_ensemble_fake`` outputs: raise instead of returning.
RAISE = object()


def make_ensemble_fake(
    outputs: dict[str, Any],
) -> tuple[Callable, collections.Counter]:
    """Build a fake ``agent_runtime.run_agent`` for roster-based tests.

    Dispatches on ``agent.name``; each arm key maps to:
    - a ``str``: returned on every call to that arm.
    - a ``list[str]``: consumed in order; the last item is repeated when
      the list is exhausted.
    - ``RAISE`` sentinel: raises ``RuntimeError`` to simulate a failed arm.

    Returns ``(fake_run_agent, counter)`` where ``counter`` is a
    ``collections.Counter`` tracking call counts per arm name.
    """
    counter: collections.Counter = collections.Counter()
    iters: dict[str, Any] = {
        k: iter(v) for k, v in outputs.items() if isinstance(v, list)
    }

    async def fake_run_agent(agent, instruction: str) -> str:
        name = agent.name
        counter[name] += 1
        output = outputs.get(name, "default answer")
        if output is RAISE:
            raise RuntimeError(f"Simulated failure for ensemble arm '{name}'")
        if isinstance(output, list):
            try:
                return next(iters[name])
            except StopIteration:
                return output[-1]
        return output

    return fake_run_agent, counter
