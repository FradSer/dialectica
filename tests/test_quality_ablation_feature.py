"""Step definitions for features/quality_ablation.feature — LLM fully mocked."""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica.agent_factory import create_agent
from evals.quality_ablation import best_of_n, self_refine

scenarios("features/quality_ablation.feature")


class _Recorder:
    def __init__(self, fake):
        self.calls = 0
        self._fake = fake

    async def __call__(self, agent, instruction: str) -> str:
        self.calls += 1
        return await self._fake(agent, instruction)


@given(
    "a mocked LLM that returns numbered candidates and picks candidate 2",
    target_fixture="recorder",
)
def best_of_n_llm():
    counter = [0]

    async def fake(agent, instruction: str) -> str:
        if instruction.lstrip().startswith("You are picking the single best"):
            return "Candidate 2 is best: 2"
        counter[0] += 1
        return f"candidate-{counter[0]}"

    return _Recorder(fake)


@given(
    "a mocked LLM that drafts, critiques, and improves",
    target_fixture="recorder",
)
def self_refine_llm():
    improve = [0]

    async def fake(agent, instruction: str) -> str:
        if instruction.lstrip().startswith("Critique this solution"):
            return "weakness: too vague"
        if instruction.lstrip().startswith("Improve the solution"):
            improve[0] += 1
            return f"improved-{improve[0]}"
        return "draft"

    return _Recorder(fake)


@when(parsers.parse("best-of-N runs with n {n:d}"), target_fixture="result")
def run_best_of_n(recorder, n: int):
    agent = create_agent(role="Generator", role_name="Solver")
    with patch("dialectica.agent_runtime.run_agent", recorder):
        return asyncio.run(best_of_n(agent, "P", n))


@when(parsers.parse("self-refine runs with {rounds:d} rounds"), target_fixture="result")
def run_self_refine(recorder, rounds: int):
    agent = create_agent(role="Generator", role_name="Solver")
    with patch("dialectica.agent_runtime.run_agent", recorder):
        return asyncio.run(self_refine(agent, "P", rounds))


@then(parsers.parse("it makes {n:d} LLM calls"))
def asserts_calls(recorder, n: int):
    assert recorder.calls == n


@then("it returns the second candidate")
def returns_second(result):
    assert result == "candidate-2"


@then("it returns the final improved solution")
def returns_final(result):
    assert result == "improved-2"
