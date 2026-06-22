"""Step definitions for features/workflow.feature — LLM fully mocked.

The primitives are driven through the same ``agent_runtime.run_agent`` seam the
rest of the suite mocks, so these tests exercise the real orchestration logic
(parallel barrier, pipeline no-barrier, schema validation, budget gate) with a
deterministic fake LLM.
"""

import asyncio
from unittest.mock import patch

from pydantic import BaseModel
from pytest_bdd import given, scenarios, then, when

from dialectica import workflow as wf
from dialectica.workflow import BudgetExhausted, Workflow

scenarios("features/workflow.feature")


# --- shared fakes ---------------------------------------------------------


class _Item(BaseModel):
    label: str
    score: int


def _call_counter():
    state = {"calls": 0, "responses": []}

    async def fake(agent, instruction: str) -> str:
        state["calls"] += 1
        return state["responses"].pop(0) if state["responses"] else "ok"

    return fake, state


# --- Scenario 1: parallel barrier + failure -> null ---------------------


@given(
    'a mocked LLM that returns a string per call and fails on "bad"',
    target_fixture="parallel_llm",
)
def parallel_llm():
    async def fake(agent, instruction: str) -> str:
        if "bad" in instruction:
            raise RuntimeError("boom")
        return instruction.replace("call:", "")

    return fake


@when("parallel runs three thunks including a failing one", target_fixture="result")
def run_parallel(parallel_llm):
    async def script():
        return await wf.parallel(
            [
                lambda: wf.agent("call:alpha"),
                lambda: wf.agent("call:bad"),
                lambda: wf.agent("call:gamma"),
            ]
        )

    with patch("dialectica.agent_runtime.run_agent", parallel_llm):
        return asyncio.run(Workflow(script).run())


@then("it returns three results with the failed one null")
def parallel_has_null(result):
    assert len(result) == 3
    assert result[1] is None


@then("the other two are their strings")
def parallel_survivors(result):
    assert result[0] == "alpha"
    assert result[2] == "gamma"


# --- Scenario 2: pipeline no-barrier --------------------------------------


@given("a mocked LLM and an increment stage", target_fixture="pipeline_setup")
def pipeline_setup():
    async def fake(agent, instruction: str) -> str:
        return instruction  # echo; stages do the real work

    def stage_upper(prev, item, index):
        async def _do():
            return await wf.agent(f"{item}-{index}")

        return _do()

    return fake, stage_upper


@when("pipeline runs three items through two stages", target_fixture="pipeline_result")
def run_pipeline(pipeline_setup):
    fake, stage_a = pipeline_setup

    async def stage_b(prev, item, index):
        return f"[{prev}]"

    async def script():
        return await wf.pipeline(["x", "y", "z"], stage_a, stage_b)

    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(Workflow(script).run())


@then("each item reaches the final stage independently")
def pipeline_final(pipeline_result):
    assert pipeline_result == ["[x-0]", "[y-1]", "[z-2]"]


# --- Scenario 3: pipeline stage throws -> item null -----------------------


@given(
    "a mocked LLM and a stage that throws on item index 1",
    target_fixture="throw_setup",
)
def throw_setup():
    async def fake(agent, instruction: str) -> str:
        return "ok"

    async def stage(prev, item, index):
        if index == 1:
            raise RuntimeError("drop this one")
        return f"{item}-{index}"

    return fake, stage


@when("pipeline runs three items", target_fixture="throw_result")
def run_pipeline_throw(throw_setup):
    fake, stage = throw_setup

    async def script():
        return await wf.pipeline(["a", "b", "c"], stage)

    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(Workflow(script).run())


@then("item 0 and item 2 survive and item 1 is null")
def pipeline_drops_one(throw_result):
    assert throw_result == ["a-0", None, "c-2"]


# --- Scenario 4: agent with schema -> validated instance -------------------


@given("a mocked LLM that returns valid JSON for a schema", target_fixture="schema_llm")
def schema_llm():
    async def fake(agent, instruction: str) -> str:
        return '{"label": "thing", "score": 7}'

    return fake


@when("agent runs with the schema", target_fixture="schema_result")
def run_agent_schema(schema_llm):
    async def script():
        return await wf.agent("judge this", schema=_Item, label="judge")

    with patch("dialectica.agent_runtime.run_agent", schema_llm):
        return asyncio.run(Workflow(script).run())


@then("it returns a validated instance with the fields")
def agent_validated(schema_result):
    assert isinstance(schema_result, _Item)
    assert schema_result.label == "thing"
    assert schema_result.score == 7


# --- Scenario 5: agent without schema -> raw text -------------------------


@given("a mocked LLM that returns prose", target_fixture="prose_llm")
def prose_llm():
    async def fake(agent, instruction: str) -> str:
        return "just some text"

    return fake


@when("agent runs without a schema", target_fixture="prose_result")
def run_agent_prose(prose_llm):
    async def script():
        return await wf.agent("hello")

    with patch("dialectica.agent_runtime.run_agent", prose_llm):
        return asyncio.run(Workflow(script).run())


@then("it returns the raw text")
def agent_raw(prose_result):
    assert prose_result == "just some text"


# --- Scenario 6: agent with schema -> null after parse failures -----------


@given("a mocked LLM that always returns unparseable JSON", target_fixture="bad_llm")
def bad_llm():
    async def fake(agent, instruction: str) -> str:
        return "this is not json at all"

    return fake


@when("agent retries a schema on unparseable output", target_fixture="bad_result")
def run_agent_bad(bad_llm):
    async def script():
        return await wf.agent("judge", schema=_Item, label="judge", max_attempts=2)

    with patch("dialectica.agent_runtime.run_agent", bad_llm):
        return asyncio.run(Workflow(script).run())


@then("it returns null")
def agent_null(bad_result):
    assert bad_result is None


# --- Scenario 6b: fenced/narrated JSON parses ----------------------------


@given(
    "a mocked LLM that returns a fenced JSON object inside prose",
    target_fixture="fenced_llm",
)
def fenced_llm():
    async def fake(agent, instruction: str) -> str:
        return 'Here is the result:\n```json\n{"label": "thing", "score": 9}\n```'

    return fake


@when(
    "agent parses the fenced response with the schema", target_fixture="fenced_result"
)
def run_agent_fenced(fenced_llm):
    async def script():
        return await wf.agent("judge this", schema=_Item, label="judge")

    with patch("dialectica.agent_runtime.run_agent", fenced_llm):
        return asyncio.run(Workflow(script).run())


@then("the fenced response yields a validated instance")
def fenced_validated(fenced_result):
    assert isinstance(fenced_result, _Item)
    assert fenced_result.label == "thing"
    assert fenced_result.score == 9


# --- Scenario 7: budget gate ---------------------------------------------


@given("a mocked LLM and a budget of one call", target_fixture="budget_setup")
def budget_setup():
    async def fake(agent, instruction: str) -> str:
        return "ok"

    return fake


@when(
    "agent runs a second time after the first consumes the budget",
    target_fixture="budget_result",
)
def run_budget(budget_setup):
    fake = budget_setup
    state = {"second": None, "raised": None}

    async def script():
        await wf.agent("first")
        try:
            await wf.agent("second")
        except BudgetExhausted as e:
            state["raised"] = str(e)
        return state

    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(Workflow(script, budget_total=1).run())


@then("it raises BudgetExhausted")
def budget_raised(budget_result):
    assert budget_result["raised"] is not None
    assert "1/1" in budget_result["raised"]


# --- Scenario 8: phase/log captured --------------------------------------


@given("a workflow script that phases and logs", target_fixture="phase_script")
def phase_script():
    # Return the script AND a holder; the script writes the run context (which
    # is only valid mid-run) into the holder before run() tears it down.
    holder = {"ctx": None}

    async def script():
        wf.phase("Gather")
        wf.log("starting")
        await wf.agent("x")
        wf.phase("Done")
        wf.log("finished")
        holder["ctx"] = wf._current.get()  # snapshot before run() returns
        return holder

    return script


@when("the workflow runs", target_fixture="phase_result")
def run_phase(phase_script):
    async def fake(agent, instruction: str) -> str:
        return "ok"

    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(Workflow(phase_script).run())


@then("the phases and log are captured on the run")
def phase_captured(phase_result):
    ctx = phase_result["ctx"]
    assert ctx is not None
    assert ctx.phases == ["Gather", "Done"]
    assert ctx.log == ["starting", "finished"]
    assert ctx.budget.spent() == 1
