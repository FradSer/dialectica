"""Step definitions for features/lcb_eval.feature — mocked LLM, real subprocess."""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from evals.baseline import SingleCallBaseline, create_baseline_agent
from evals.code_eval import run_rescue_eval
from evals.lcb import LcbCase, LcbProblem, build_lcb_statement, verify_stdin_solution
from examples.patterns.tot_gan_pattern import create_coordinator

scenarios("features/lcb_eval.feature")

DOUBLER = LcbProblem(
    id="doubler",
    title="Double the numbers",
    platform="atcoder",
    contest_date="2025-03",
    content="Read N, then N integers; print each doubled, one per line.",
    cases=[
        LcbCase(input="2\n3\n5\n", output="6\n10\n"),
        LcbCase(input="1\n0\n", output="0\n"),
    ],
)

CORRECT = """\
n = int(input())
for _ in range(n):
    print(int(input()) * 2)
"""

WRONG = """\
n = int(input())
for _ in range(n):
    print(int(input()) * 3)
"""

HANGING = "while True:\n    pass\n"

TRAILING = """\
import sys
n = int(input())
for _ in range(n):
    sys.stdout.write(str(int(input()) * 2) + "  \\n")
"""


@given("an lcb problem that doubles each input number", target_fixture="lcb_problem")
def lcb_problem():
    return DOUBLER


@when("a correct stdin solution is verified", target_fixture="stdin_verdict")
def verify_correct(lcb_problem):
    return verify_stdin_solution(CORRECT, lcb_problem.cases)


@when("an incorrect stdin solution is verified", target_fixture="stdin_verdict")
def verify_wrong(lcb_problem):
    return verify_stdin_solution(WRONG, lcb_problem.cases)


@when("a non-terminating stdin solution is verified", target_fixture="stdin_verdict")
def verify_hanging(lcb_problem):
    return verify_stdin_solution(HANGING, lcb_problem.cases, timeout_per_case=2)


@when(
    "a correct solution with trailing whitespace is verified",
    target_fixture="stdin_verdict",
)
def verify_trailing(lcb_problem):
    return verify_stdin_solution(TRAILING, lcb_problem.cases)


@then("the stdin verification passes")
def stdin_passes(stdin_verdict):
    assert stdin_verdict.passed is True


@then("the stdin verification fails")
def stdin_fails(stdin_verdict):
    assert stdin_verdict.passed is False


@given(
    "a mocked LLM where the baseline fails the doubling problem but the engine solves it",
    target_fixture="lcb_llm",
)
def lcb_llm():
    async def fake(agent, instruction: str) -> str:
        if agent.name == "Baseline":
            return f"```python\n{WRONG}```"
        if agent.name == "synthesizer":
            return f"```python\n{CORRECT}```"
        if agent.name == "discriminator":
            return '{"score": 8.0, "reasoning": "ok"}'
        return "1. Parse then double\n2. Stream the output"

    return fake


@when("the lcb rescue eval runs", target_fixture="lcb_report")
def run_lcb_rescue(lcb_llm):
    def engine_factory(statement: str):
        return create_coordinator(
            problem=statement, max_depth=2, beam_width=2, max_gan_rounds=1
        )

    baseline = SingleCallBaseline(create_baseline_agent())
    with patch("dialectica.agent_runtime.run_agent", lcb_llm):
        return asyncio.run(
            run_rescue_eval(
                [DOUBLER],
                engine_factory=engine_factory,
                baseline=baseline,
                screen_attempts=2,
                verifier=lambda problem, code: verify_stdin_solution(
                    code, problem.cases
                ),
                statement_builder=build_lcb_statement,
            )
        )


@then(parsers.parse("the lcb engine attempts {n:d} problem"))
def lcb_engine_attempts(lcb_report, n: int):
    assert len(lcb_report.attempted) == n


@then(parsers.parse("the lcb rescue count is {n:d}"))
def lcb_rescue_count(lcb_report, n: int):
    assert lcb_report.rescued == n
