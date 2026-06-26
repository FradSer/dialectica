"""Deterministic mock helpers shared across the mocked tests."""

import collections
import json
from collections.abc import Callable
from typing import Any

#: Sentinel value for ``make_ensemble_fake`` outputs: raise instead of returning.
RAISE = object()


def verdict_json(
    score: float,
    flaws: list[str] | None = None,
    suggestions: list[str] | None = None,
    should_terminate: bool = False,
    reasoning: str = "ok",
) -> str:
    """Serialize a DiscriminatorVerdict the way the structured-output LLM would."""
    return json.dumps(
        {
            "score": score,
            "flaws": flaws or [],
            "suggestions": suggestions or [],
            "should_terminate": should_terminate,
            "reasoning": reasoning,
        }
    )


def make_call_agent(
    verdicts: list[dict],
    *,
    refined: str = "A refined, stronger thought.",
    strategies: str = "1. First strategy\n2. Second strategy\n3. Third strategy",
    final: str = "FINAL SYNTHESIZED ANSWER",
):
    """Build an async stand-in for ``_call_agent`` that dispatches by agent role.

    ``verdicts`` is consumed one entry per Discriminator call (each a dict of
    DiscriminatorVerdict fields, e.g. ``{"score": 8.0}``). Generators return a
    numbered list for strategy/child generation and ``refined`` when refining;
    the Synthesizer returns ``final``.
    """
    verdict_iter = iter(verdicts)

    async def fake_call_agent(agent, instruction: str) -> str:
        name = agent.name
        if "Discriminator" in name:
            return verdict_json(**next(verdict_iter))
        if name == "Synthesizer":
            return final
        if "Generator" in name:
            if "Refine the following thought" in instruction:
                return refined
            return strategies
        return ""

    return fake_call_agent


def make_constant_call_agent(score: float, **kwargs):
    """Like ``make_call_agent`` but the Discriminator always returns ``score``."""
    base = make_call_agent([], **kwargs)

    async def fake_call_agent(agent, instruction: str) -> str:
        if "Discriminator" in agent.name:
            return verdict_json(score)
        return await base(agent, instruction)

    return fake_call_agent


def make_ensemble_fake(
    outputs: dict[str, Any],
) -> tuple[Callable, collections.Counter]:
    """Build a fake ``agent_runtime.run_agent`` for ensemble tests.

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
