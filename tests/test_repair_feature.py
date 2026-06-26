"""Step definitions for features/repair.feature.

Mocks the LLM seam (agent_runtime.run_agent) and injects a scripted verifier,
exercising the real repair control flow: solve -> verify -> repair-on-failure.
"""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import create_repair_engine
from tests.helpers import make_ensemble_fake

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


@when("the repair engine runs", target_fixture="result")
def run_repair(ctx):
    if "models" in ctx:
        verdicts = list(ctx["verdicts"])

        def verifier(answer: str) -> tuple[bool, str]:
            return verdicts.pop(0) if verdicts else (False, "no more verdicts")

        engine = create_repair_engine(
            "solve the problem",
            verifier=verifier,
            max_attempts=ctx["max_attempts"],
            models=ctx["models"],
        )
        fake, _ = make_ensemble_fake(ctx["model_outputs"])
        with patch("dialectica.agent_runtime.run_agent", fake):
            return asyncio.run(engine.run())

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


# --- Roster scenarios ---


@given(
    'a repair engine whose generator is a roster of models "A" and "B"',
    target_fixture="ctx",
)
def ctx_roster():
    return {
        "models": ["A", "B"],
        "model_outputs": {"A": [], "B": []},
        "verdicts": [],
        "max_attempts": 3,
    }


@given('model "A" produces a solution that fails the verifier')
def model_a_fails(ctx: dict):
    ctx["model_outputs"]["A"].append("answer-from-A")
    ctx["verdicts"].append((False, "A answer failed"))


@given('model "B" produces a solution that passes the verifier')
def model_b_passes(ctx: dict):
    ctx["model_outputs"]["B"].append("answer-from-B")
    ctx["verdicts"].append((True, ""))


@given("max 3 attempts where no model ever passes the verifier")
def max_3_never_pass(ctx: dict):
    ctx["max_attempts"] = 3
    ctx["model_outputs"]["A"].extend(["answer-A1", "answer-A2"])
    ctx["model_outputs"]["B"].append("answer-B1")
    ctx["verdicts"].extend(
        [(False, "A1 failed"), (False, "B1 failed"), (False, "A2 failed")]
    )


@then(parsers.re(r'attempt (?P<n>\d+) was produced by model "(?P<m>\w+)"'))
def attempt_by_model(result, n: str, m: str):
    entry = result["history"][int(n) - 1]
    assert entry["model"] == m, f"expected model '{m}', got '{entry['model']}'"


@then("every attempt was produced by the same single model")
def same_single_model(result):
    models = [entry["model"] for entry in result["history"]]
    assert len(set(models)) == 1, f"expected all the same model, got {models}"


@then('the attempts were produced by models "A", "B", "A" in order')
def attempts_a_b_a(result):
    actual = [entry["model"] for entry in result["history"]]
    assert actual == ["A", "B", "A"], f"expected ['A', 'B', 'A'], got {actual}"


@when(
    "a repair engine is created with both model_config and models set",
    target_fixture="result",
)
def create_conflicting():
    exc: Exception | None = None
    try:
        create_repair_engine(
            "problem",
            verifier=lambda a: (True, ""),
            model_config="google:gemini-3.5-flash",
            models=["A", "B"],
        )
    except Exception as e:
        exc = e
    return {"error": exc}


@then("construction fails with a conflicting-config error")
def conflicting_config_error(result):
    assert isinstance(result["error"], ValueError), (
        f"expected ValueError, got {type(result['error'])}: {result['error']}"
    )


def test_roster_configs_are_parsed_to_resolved_models():
    """C2 regression guard: repair roster 'provider:model' configs must be
    resolved before create_agent (else a non-google arm never wraps in LiteLlm
    and never routes). The history label keeps the raw config for attribution.
    """
    engine = create_repair_engine(
        "p", verifier=lambda a: (True, ""), models=["google:gemini-3.5-flash"]
    )
    assert engine._generators[0].model == "gemini-3.5-flash"
    assert engine._labels[0] == "google:gemini-3.5-flash"
