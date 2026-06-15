"""Step definitions for features/dialectic.feature.

Mocks the single LLM seam (agent_runtime.run_agent) and exercises the real
dialectic control flow: tension identification, the NONE fast-path, the
thesis/antithesis/synthesis spiral, and EXHAUSTED semantic convergence.
The mock dispatches by agent name + prompt template, never by patching the
kernel itself.
"""

import asyncio
import json
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import create_dialectic_engine

scenarios("features/dialectic.feature")


def make_dialectic_llm(ctx: dict):
    """Async run_agent stand-in dispatching by role and prompt template."""
    state = {"score_calls": 0, "antithesis_calls": 0}
    ctx.setdefault("discriminator_instructions", [])
    ctx.setdefault("antithesis_instructions", [])

    async def fake(agent, instruction: str) -> str:
        name = agent.name
        if name == "Discriminator":
            ctx["discriminator_instructions"].append(instruction)
            # Simulate the ~7-10% transient empty/garbage verdict some proxies
            # return: fail once, before the index logic, so the retry lands on
            # the real score.
            if ctx.get("first_score_unparseable") and not state.get("failed_once"):
                state["failed_once"] = True
                return "not a verdict at all"
            i = state["score_calls"]
            state["score_calls"] += 1
            scores = ctx["synth_scores"]
            score = (
                ctx["thesis_score"] if i == 0 else scores[min(i - 1, len(scores) - 1)]
            )
            return json.dumps({"score": score, "reasoning": "ok"})
        if name == "Synthesizer":
            return "SYNTHESIS"
        # Proposer handles tension / thesis / antithesis, told apart by prompt.
        ctx["proposer_system"] = agent.instruction
        if "genuine dialectical tension" in instruction:
            return ctx["tension"]
        if "single best solution" in instruction:
            ctx["thesis_instruction"] = instruction
            return "THESIS"
        ctx["antithesis_instructions"].append(instruction)
        state["antithesis_calls"] += 1
        if (
            ctx["exhausted_after"] is not None
            and state["antithesis_calls"] > ctx["exhausted_after"]
        ):
            return "EXHAUSTED"
        if ctx.get("multi_rival_response"):
            return ctx["multi_rival_response"]
        return "A complete rival solution built on the opposite principle."

    return fake


def _default_ctx(max_rounds: int = 3) -> dict:
    return {
        "max_rounds": max_rounds,
        "perspectives": 1,
        "tension": "X vs Y — the crux",
        "exhausted_after": None,
        "thesis_score": 8.0,
        "synth_scores": [9.0, 9.5, 9.8],
    }


@given("a dialectic engine", target_fixture="ctx")
def ctx_default():
    return _default_ctx()


@given(parsers.parse("a dialectic engine with max rounds {n:d}"), target_fixture="ctx")
def ctx_max_rounds(n: int):
    return _default_ctx(max_rounds=n)


@given("the problem has no genuine tension")
def no_tension(ctx):
    ctx["tension"] = "NONE"


@given(parsers.parse('the problem\'s core tension is "{t}"'))
def set_tension(ctx, t: str):
    ctx["tension"] = f"{t} — the crux of the problem"


@given("each synthesis surpasses its thesis")
def synth_surpasses(ctx):
    ctx["synth_scores"] = [9.0, 9.5, 9.8]  # all above thesis_score 8.0


@given(parsers.parse("the opposition is exhausted after {n:d} round"))
def exhausted_after(ctx, n: int):
    ctx["exhausted_after"] = n


@given("the first scoring verdict comes back unparseable")
def first_score_unparseable(ctx):
    ctx["first_score_unparseable"] = True


@given(parsers.parse("the adversary explores {n:d} perspectives"))
def set_perspectives(ctx, n: int):
    ctx["perspectives"] = n


@given("each rival contains its own internal steps")
def multi_rival_with_steps(ctx):
    # Two whole rival solutions, each carrying its own numbered sub-steps, kept
    # apart by the explicit delimiter. A numbered-list parser would shatter
    # these on the "1./2." markers; an explicit delimiter keeps each whole.
    ctx["multi_rival_response"] = (
        "Rival one: distribute the work.\n"
        "1. split into teams\n"
        "2. sync weekly\n"
        "===NEXT===\n"
        "Rival two: centralize control.\n"
        "1. one owner\n"
        "2. daily standup"
    )


@when("the dialectic runs", target_fixture="result")
def run_dialectic(ctx):
    engine = create_dialectic_engine(
        "test problem",
        max_rounds=ctx["max_rounds"],
        perspectives=ctx["perspectives"],
    )
    with patch("dialectica.agent_runtime.run_agent", make_dialectic_llm(ctx)):
        return asyncio.run(engine.run())


@then("it is not dialecticized")
def not_dialecticized(result):
    assert result["dialecticized"] is False


@then("the answer is the direct thesis")
def answer_is_thesis(result):
    assert result["final_answer"] == "THESIS"


@then("no antithesis was raised")
def no_antithesis(result):
    assert all(h["role"] != "antithesis" for h in result["history"])


@then("it is dialecticized")
def is_dialecticized(result):
    assert result["dialecticized"] is True


@then("the trace identifies the tension before the thesis")
def tension_before_thesis(result):
    roles = [h["role"] for h in result["history"]]
    assert roles[0] == "tension"
    assert roles[1] == "thesis"


@then("the answer is the final synthesis")
def answer_is_synthesis(result):
    assert result["final_answer"] == "SYNTHESIS"


@then(parsers.parse("the dialectic ran {n:d} round"))
def ran_rounds(result, n: int):
    assert result["rounds"] == n


@then("convergence was by exhaustion, not by reaching max rounds")
def by_exhaustion(result, ctx):
    assert result["rounds"] < ctx["max_rounds"]


@then("every scoring call saw the problem statement")
def scoring_saw_problem(ctx):
    calls = ctx["discriminator_instructions"]
    assert calls, "expected at least one discriminator scoring call"
    assert all("test problem" in instr for instr in calls), (
        "discriminator scored a solution without the problem in context"
    )


@then("the thesis kept its real score despite the transient failure")
def thesis_kept_real_score(result, ctx):
    thesis = next(h for h in result["history"] if h["role"] == "thesis")
    assert thesis["score"] == ctx["thesis_score"], (
        "a transient unparseable verdict was scored 0 instead of being re-asked"
    )


@then("the proposer was framed for committed dialectical positions")
def proposer_framed_dialectic(ctx):
    assert "operating inside a dialectic" in ctx["proposer_system"], (
        "the proposer kept the generic breadth-first ToT persona"
    )


@then("the thesis was generated against the evaluation criteria")
def thesis_has_criteria(ctx):
    assert "Feasibility under stated constraints" in ctx["thesis_instruction"], (
        "the thesis was proposed without the feasibility criteria"
    )


@then("every antithesis was generated against the evaluation criteria")
def antithesis_has_criteria(ctx):
    calls = ctx["antithesis_instructions"]
    assert calls, "expected at least one antithesis call"
    assert all("Feasibility under stated constraints" in instr for instr in calls), (
        "a rival was proposed without the feasibility criteria"
    )


@then("both rival solutions were kept whole")
def rivals_kept_whole(result):
    antitheses = [h["text"] for h in result["history"] if h["role"] == "antithesis"]
    assert len(antitheses) == 2, f"expected 2 whole rivals, got {len(antitheses)}"
    assert "Rival one" in antitheses[0] and "split into teams" in antitheses[0]
    assert "Rival two" in antitheses[1] and "one owner" in antitheses[1]
