"""Step definitions for features/eval_harness.feature — mocked LLM."""

import asyncio
import json
from unittest.mock import patch

from helpers import make_constant_call_agent
from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import agent_runtime
from dialectica.agent import create_coordinator
from evals.baseline import SingleCallBaseline, create_baseline_agent
from evals.harness import count_agent_calls, run_eval
from evals.judge import BlindJudge, create_judge_agent
from evals.problems import EvalProblem

scenarios("features/eval_harness.feature")

ENGINE_ANSWER = "FINAL SYNTHESIZED ANSWER"
BASELINE_ANSWER = "BASELINE ANSWER"


def judge_verdict(winner: str) -> str:
    return json.dumps({"winner": winner, "reasoning": "r"})


def make_judge_fake(policy: str):
    """Async run_agent stand-in for the Judge.

    Policies: ``prefers_engine`` picks whichever position holds the engine
    answer, ``position_a`` always picks A, ``malformed`` returns non-JSON.
    """

    async def fake(agent, instruction: str) -> str:
        if policy == "malformed":
            return "this is not a JSON verdict"
        if policy == "position_a":
            return judge_verdict("A")
        a_start = instruction.index("**Answer A:**")
        b_start = instruction.index("**Answer B:**")
        in_position_a = ENGINE_ANSWER in instruction[a_start:b_start]
        return judge_verdict("A" if in_position_a else "B")

    return fake


def make_full_fake():
    """Dispatch by role: Judge prefers the engine, Baseline answers once,
    everything else behaves like the standard mocked engine pipeline."""
    engine_fake = make_constant_call_agent(8.0)
    judge_fake = make_judge_fake("prefers_engine")

    async def fake(agent, instruction: str) -> str:
        if agent.name == "Judge":
            return await judge_fake(agent, instruction)
        if agent.name == "Baseline":
            return BASELINE_ANSWER
        return await engine_fake(agent, instruction)

    return fake


@given(
    "a blind judge whose model always prefers the engine answer",
    target_fixture="judge_llm",
)
def judge_llm_prefers_engine():
    return make_judge_fake("prefers_engine")


@given(
    "a blind judge whose model always prefers position A",
    target_fixture="judge_llm",
)
def judge_llm_position_biased():
    return make_judge_fake("position_a")


@given(
    "a blind judge whose model returns malformed verdicts",
    target_fixture="judge_llm",
)
def judge_llm_malformed():
    return make_judge_fake("malformed")


@when(
    "the judge compares an engine answer and a baseline answer",
    target_fixture="comparison",
)
def compare(judge_llm):
    judge = BlindJudge(create_judge_agent())
    with patch("dialectica.agent_runtime.run_agent", judge_llm):
        return asyncio.run(judge.compare("p", ENGINE_ANSWER, BASELINE_ANSWER))


@then(parsers.parse('the comparison winner is "{winner}"'))
def comparison_winner_is(comparison, winner: str):
    assert comparison.winner == winner


@given(
    "an eval harness with a mocked LLM that favors the engine",
    target_fixture="harness_llm",
)
def harness_llm():
    return make_full_fake()


@when(parsers.parse("the harness evaluates {n:d} problem"), target_fixture="report")
def evaluate(harness_llm, n: int):
    problems = [
        EvalProblem(id=f"p{i}", statement=f"benchmark problem {i}") for i in range(n)
    ]

    def engine_factory(statement: str):
        return create_coordinator(
            problem=statement, max_depth=2, beam_width=2, max_gan_rounds=1
        )

    baseline = SingleCallBaseline(create_baseline_agent())
    judge = BlindJudge(create_judge_agent())
    with patch("dialectica.agent_runtime.run_agent", harness_llm):
        return asyncio.run(
            run_eval(
                problems,
                engine_factory=engine_factory,
                baseline=baseline,
                judge=judge,
            )
        )


@then(parsers.parse("the report has {n:d} result with both answers"))
def report_has_results(report, n: int):
    assert len(report.results) == n
    result = report.results[0]
    assert result.engine_answer == ENGINE_ANSWER
    assert result.baseline_answer == BASELINE_ANSWER


@then("the engine used more LLM calls than the baseline")
def engine_used_more_calls(report):
    result = report.results[0]
    assert result.baseline_calls == 1
    assert result.engine_calls > result.baseline_calls


@then(parsers.parse("the aggregate shows {n:d} engine win"))
def aggregate_engine_wins(report, n: int):
    assert report.engine_wins == n
    assert report.baseline_wins == 0


@given("a mocked LLM", target_fixture="plain_llm")
def plain_llm():
    async def fake(agent, instruction: str) -> str:
        return "ok"

    return fake


@when(
    parsers.parse("{n:d} agent calls run inside the call counter"),
    target_fixture="counter",
)
def run_calls_inside_counter(plain_llm, n: int):
    agent = create_baseline_agent()

    async def go():
        with count_agent_calls() as counter:
            for _ in range(n):
                await agent_runtime.run_agent(agent, "x")
        return counter

    with patch("dialectica.agent_runtime.run_agent", plain_llm):
        return asyncio.run(go())


@then(parsers.parse("the counter reports {n:d} calls"))
def counter_reports(counter, n: int):
    assert counter.count == n
