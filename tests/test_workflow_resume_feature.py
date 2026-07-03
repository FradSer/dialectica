"""Step definitions for features/workflow_resume.feature."""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, scenarios, then, when

from dialectica import workflow as wf
from dialectica.workflow import Workflow
from dialectica.workflow_journal import RunJournal

scenarios("features/workflow_resume.feature")


@given("a mocked LLM", target_fixture="simple_llm")
def simple_llm():
    async def fake(agent, instruction: str) -> str:
        return "ok"

    return fake


@given("a mocked LLM that counts calls", target_fixture="counting_llm")
def counting_llm():
    state = {"calls": 0}

    async def fake(agent, instruction: str) -> str:
        state["calls"] += 1
        return f"answer-{state['calls']}"

    return fake, state


@when("a workflow runs two agent calls", target_fixture="journal_entries")
def run_two_agents(simple_llm, tmp_path):
    journal_dir = tmp_path / "journals"

    async def script():
        await wf.agent("one")
        await wf.agent("two")
        return wf.run_id()

    with patch("dialectica.agent_runtime.run_agent", simple_llm):
        run_id = asyncio.run(Workflow(script, journal_dir=journal_dir).run())
    journal = RunJournal.load(run_id, journal_dir)
    return journal.entries


@then("the journal records 2 entries")
def journal_has_two(journal_entries):
    assert len(journal_entries) == 2


@when(
    "the same workflow is resumed with the prior run id", target_fixture="resume_calls"
)
def resume_same_script(counting_llm, tmp_path):
    fake, state = counting_llm
    journal_dir = tmp_path / "journals"
    holder = {"run_id": None}

    async def script():
        await wf.agent("one")
        await wf.agent("two")
        holder["run_id"] = wf.run_id()
        return "done"

    with patch("dialectica.agent_runtime.run_agent", fake):
        asyncio.run(Workflow(script, journal_dir=journal_dir).run())
        state["calls"] = 0
        asyncio.run(
            Workflow(
                script,
                journal_dir=journal_dir,
                resume_run_id=holder["run_id"],
            ).run()
        )
    return state["calls"]


@then("no LLM calls were made on resume")
def no_calls_on_resume(resume_calls):
    assert resume_calls == 0


@when("the workflow resumes with different args", target_fixture="resume_diff_calls")
def resume_different_args(counting_llm, tmp_path):
    fake, state = counting_llm
    journal_dir = tmp_path / "journals"
    holder = {"run_id": None}

    async def script():
        await wf.agent("one")
        holder["run_id"] = wf.run_id()
        return "done"

    with patch("dialectica.agent_runtime.run_agent", fake):
        asyncio.run(Workflow(script, args={"a": 1}, journal_dir=journal_dir).run())
        state["calls"] = 0
        asyncio.run(
            Workflow(
                script,
                args={"a": 2},
                journal_dir=journal_dir,
                resume_run_id=holder["run_id"],
            ).run()
        )
    return state["calls"]


@then("the LLM was called again on resume")
def calls_on_resume(resume_diff_calls):
    assert resume_diff_calls >= 1


@when("a workflow script reads run_id", target_fixture="seen_run_id")
def read_run_id(simple_llm, tmp_path):
    journal_dir = tmp_path / "journals"

    async def script():
        return wf.run_id()

    with patch("dialectica.agent_runtime.run_agent", simple_llm):
        return asyncio.run(Workflow(script, journal_dir=journal_dir).run())


@then("the run id is a non-empty string")
def run_id_nonempty(seen_run_id):
    assert isinstance(seen_run_id, str)
    assert seen_run_id
