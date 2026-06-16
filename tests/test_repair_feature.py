"""Step definitions for features/repair.feature.

Mocks the LLM seam (agent_runtime.run_agent) and injects a scripted verifier,
exercising the real repair control flow: solve -> verify -> repair-on-failure.
"""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import create_repair_engine

scenarios("features/repair.feature")


def make_run_agent(ctx: dict):
    answers = list(ctx["answers"])

    async def fake(agent, instruction: str) -> str:
        ctx["instructions"].append(instruction)
        return answers.pop(0) if answers else "exhausted"

    return fake


def make_engine(ctx: dict):
    verdicts = list(ctx["verdicts"])

    def verifier(answer: str) -> tuple[bool, str]:
        return verdicts.pop(0) if verdicts else (False, "no more verdicts")

    return create_repair_engine(
        "solve the problem", verifier=verifier, max_attempts=ctx["max_attempts"]
    )


@given("a repair engine whose first solution passes", target_fixture="ctx")
def ctx_pass():
    return {
        "verdicts": [(True, "")],
        "answers": ["def f(): return 1"],
        "max_attempts": 3,
        "instructions": [],
    }


@given("a repair engine whose first solution fails then is fixed", target_fixture="ctx")
def ctx_fail_then_fix():
    return {
        "verdicts": [(False, "AssertionError: expected 5 got 4"), (True, "")],
        "answers": ["broken solution", "fixed solution"],
        "max_attempts": 3,
        "instructions": [],
    }


@given(
    "a repair engine with max 2 attempts whose solution never passes",
    target_fixture="ctx",
)
def ctx_never():
    return {
        "verdicts": [(False, "err1"), (False, "err2")],
        "answers": ["a", "b"],
        "max_attempts": 2,
        "instructions": [],
    }


@given(
    "a repair engine (max 3) that keeps returning the same failing solution",
    target_fixture="ctx",
)
def ctx_no_progress():
    # Same solution every time: attempt 2 repeats attempt 1, so the engine must
    # stop at 2 rather than burn the 3rd attempt re-verifying identical code.
    return {
        "verdicts": [(False, "stuck"), (False, "stuck"), (False, "stuck")],
        "answers": ["SAME", "SAME", "SAME"],
        "max_attempts": 3,
        "instructions": [],
    }


@when("the repair engine runs", target_fixture="result")
def run_repair(ctx):
    engine = make_engine(ctx)
    with patch("dialectica.agent_runtime.run_agent", make_run_agent(ctx)):
        return asyncio.run(engine.run())


@then("the solution passed")
def solution_passed(result):
    assert result["passed"] is True


@then("the solution did not pass")
def solution_not_passed(result):
    assert result["passed"] is False


@then(parsers.re(r"it took (?P<n>\d+) attempts?"))
def took_attempts(result, n: str):
    assert result["attempts"] == int(n)


@then("the repair prompt carried the verifier feedback")
def repair_carried_feedback(ctx):
    # instructions[0] is the solve prompt; the repair prompt(s) follow and must
    # contain the concrete failure the engine is repairing against.
    assert any(
        "AssertionError: expected 5 got 4" in instr for instr in ctx["instructions"][1:]
    ), "the repair prompt did not include the verifier feedback"
