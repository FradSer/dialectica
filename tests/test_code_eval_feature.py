"""Step definitions for features/code_eval.feature — mocked LLM, real subprocess."""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from evals.baseline import SingleCallBaseline, create_baseline_agent
from evals.code_eval import (
    extract_python_code,
    run_code_eval,
    run_rescue_eval,
    verify_solution,
)
from evals.code_problems import CodeProblem
from examples.patterns.tot_gan_pattern import create_coordinator

scenarios("features/code_eval.feature")

ADD_TWO = CodeProblem(
    id="add_two",
    prompt="def add_two(x: int, y: int) -> int:\n"
    '    """Return the sum of x and y."""\n',
    entry_point="add_two",
    tests="assert add_two(1, 2) == 3\nassert add_two(-1, 1) == 0\n",
)

CORRECT = "def add_two(x: int, y: int) -> int:\n    return x + y\n"
WRONG = "def add_two(x: int, y: int) -> int:\n    return x - y\n"
LOOPING = "def add_two(x: int, y: int) -> int:\n    while True:\n        pass\n"


@given("an answer containing a python code block among prose", target_fixture="answer")
def prose_answer():
    return (
        "Here is my solution, explained step by step.\n\n"
        "```python\n"
        f"{CORRECT}"
        "```\n\n"
        "This handles negatives too."
    )


@when("the code is extracted", target_fixture="extracted")
def extract(answer):
    return extract_python_code(answer)


@then("the extracted code contains the function definition only")
def extracted_is_clean(extracted):
    assert extracted.strip() == CORRECT.strip()
    assert "explained" not in extracted


@given(parsers.parse('the code problem "{problem_id}"'), target_fixture="problem")
def code_problem(problem_id: str):
    assert problem_id == ADD_TWO.id
    return ADD_TWO


@when("a correct implementation is verified", target_fixture="verdict")
def verify_correct(problem):
    return verify_solution(problem, CORRECT)


@when("an incorrect implementation is verified", target_fixture="verdict")
def verify_incorrect(problem):
    return verify_solution(problem, WRONG)


@when("a non-terminating implementation is verified", target_fixture="verdict")
def verify_looping(problem):
    return verify_solution(problem, LOOPING, timeout=2)


@then("the verification passes")
def verification_passes(verdict):
    assert verdict.passed is True


@then("the verification fails")
def verification_fails(verdict):
    assert verdict.passed is False


@given(
    "a mocked LLM whose engine answers are correct and baseline answers are wrong",
    target_fixture="code_llm",
)
def code_llm():
    async def fake(agent, instruction: str) -> str:
        if agent.name == "Baseline":
            return f"```python\n{WRONG}```"
        if agent.name == "synthesizer":
            return f"```python\n{CORRECT}```"
        if agent.name == "discriminator":
            return '{"score": 8.0, "reasoning": "ok"}'
        return "1. Implement directly\n2. Use builtins"

    return fake


@when(
    parsers.parse("the code eval runs on {n:d} problems"),
    target_fixture="code_report",
)
def run_eval_on_problems(code_llm, n: int):
    problems = [ADD_TWO.model_copy(update={"id": f"add_two_{i}"}) for i in range(n)]

    def engine_factory(statement: str):
        return create_coordinator(
            problem=statement, max_depth=2, beam_width=2, max_gan_rounds=1
        )

    baseline = SingleCallBaseline(create_baseline_agent())
    with patch("dialectica.agent_runtime.run_agent", code_llm):
        return asyncio.run(
            run_code_eval(problems, engine_factory=engine_factory, baseline=baseline)
        )


@then(parsers.parse("the engine pass rate is {passed:d} of {total:d}"))
def engine_pass_rate(code_report, passed: int, total: int):
    assert code_report.engine_passed == passed
    assert len(code_report.results) == total


@then(parsers.parse("the baseline pass rate is {passed:d} of {total:d}"))
def baseline_pass_rate(code_report, passed: int, total: int):
    assert code_report.baseline_passed == passed


SUB_TWO = CodeProblem(
    id="sub_two",
    prompt='def sub_two(x: int, y: int) -> int:\n    """Return x minus y."""\n',
    entry_point="sub_two",
    tests="assert sub_two(3, 2) == 1\nassert sub_two(1, 1) == 0\n",
)

SUB_CORRECT = "def sub_two(x: int, y: int) -> int:\n    return x - y\n"


@given(
    "a mocked LLM where the baseline only solves the addition problem",
    target_fixture="rescue_llm",
)
def rescue_llm():
    async def fake(agent, instruction: str) -> str:
        if agent.name == "Baseline":
            return f"```python\n{CORRECT}```"  # only correct for add_two
        if agent.name == "synthesizer":
            return f"```python\n{SUB_CORRECT}```"
        if agent.name == "discriminator":
            return '{"score": 8.0, "reasoning": "ok"}'
        return "1. Implement directly\n2. Use builtins"

    return fake


@when(
    "the rescue eval runs on the addition and subtraction problems",
    target_fixture="rescue_report",
)
def run_rescue(rescue_llm):
    def engine_factory(statement: str):
        return create_coordinator(
            problem=statement, max_depth=2, beam_width=2, max_gan_rounds=1
        )

    baseline = SingleCallBaseline(create_baseline_agent())
    with patch("dialectica.agent_runtime.run_agent", rescue_llm):
        return asyncio.run(
            run_rescue_eval(
                [ADD_TWO, SUB_TWO],
                engine_factory=engine_factory,
                baseline=baseline,
                screen_attempts=2,
            )
        )


@then(parsers.parse("the baseline screen solves {n:d} problem"))
def baseline_screen_solves(rescue_report, n: int):
    assert rescue_report.baseline_solved == [ADD_TWO.id][:n]


@then(parsers.parse("the engine attempts {n:d} problem"))
def engine_attempts(rescue_report, n: int):
    assert len(rescue_report.attempted) == n
    assert rescue_report.attempted[0].problem_id == SUB_TWO.id
    assert rescue_report.attempted[0].engine_calls > 1


@then(parsers.parse("the rescue count is {n:d}"))
def rescue_count(rescue_report, n: int):
    assert rescue_report.rescued == n
