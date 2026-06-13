"""Step definitions for features/engine.feature — mocked LLM, no network."""

import asyncio
from unittest.mock import patch

from helpers import make_constant_call_agent
from pytest_bdd import given, parsers, scenarios, then, when

from dialectica.agent import create_coordinator

scenarios("features/engine.feature")


@given(
    parsers.parse(
        "the default pipeline with max depth {depth:d} and beam width {width:d}"
    ),
    target_fixture="coordinator",
)
def coordinator(depth: int, width: int):
    return create_coordinator(
        problem="How do we test the default composition?",
        max_depth=depth,
        beam_width=width,
        max_gan_rounds=1,
        score_threshold=7.0,
    )


@given(parsers.parse("every thought is scored {score:g}"), target_fixture="fake_llm")
def fake_llm(score: float):
    return make_constant_call_agent(score)


@when("the engine runs", target_fixture="result")
def run_engine(coordinator, fake_llm):
    with patch("dialectica.agent_runtime.run_agent", fake_llm):
        return asyncio.run(coordinator.run())


@given(
    "the generator returns nothing on its first call then recovers",
    target_fixture="fake_llm",
)
def flaky_generator():
    state = {"first_expand": True}

    async def fake(agent, instruction: str) -> str:
        is_expand = (
            "Generator" in agent.name and "Refine the following" not in instruction
        )
        if is_expand:
            if state.pop("first_expand", False):
                return ""  # degraded model: empty strategy list on first try
            return "1. First strategy\n2. Second strategy"
        if "Discriminator" in agent.name:
            return '{"score": 8.0, "reasoning": "ok"}'
        if agent.name == "Synthesizer":
            return "FINAL SYNTHESIZED ANSWER"
        return "refined"

    return fake


@when("the engine runs after the flaky generator", target_fixture="result")
def run_after_flaky(coordinator, fake_llm):
    with patch("dialectica.agent_runtime.run_agent", fake_llm):
        return asyncio.run(coordinator.run())


@then(parsers.parse("the tree contains more than {count:d} thought"))
def tree_size_more_than(result, count: int):
    assert result["stats"]["total_thoughts"] > count


class ConcurrencyProbe:
    """Wraps a fake LLM and records how many calls overlap in time."""

    def __init__(self, inner):
        self.inner = inner
        self.in_flight = 0
        self.max_in_flight = 0

    async def __call__(self, agent, instruction: str) -> str:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.005)  # let concurrent calls overlap
            return await self.inner(agent, instruction)
        finally:
            self.in_flight -= 1


@when("the engine runs with a concurrency probe", target_fixture="result")
def run_engine_with_probe(coordinator, fake_llm, request):
    probe = ConcurrencyProbe(fake_llm)
    request.config._concurrency_probe = probe
    with patch("dialectica.agent_runtime.run_agent", probe):
        return asyncio.run(coordinator.run())


@then(parsers.parse("at least {n:d} LLM calls were in flight simultaneously"))
def calls_overlapped(request, n: int):
    assert request.config._concurrency_probe.max_in_flight >= n


@then(parsers.parse('the final answer is "{answer}"'))
def final_answer_is(result, answer: str):
    assert result["final_answer"] == answer


@then(parsers.parse("the tree contains {count:d} thoughts"))
def tree_size_is(result, count: int):
    assert result["stats"]["total_thoughts"] == count


@then("the best path starts at the root")
def best_path_starts_at_root(result):
    assert result["best_path"][0] == "root"
    assert len(result["best_path"]) >= 2


@then("the beam is empty")
def beam_is_empty(coordinator):
    assert coordinator.active_beam == []
