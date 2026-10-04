"""Given typed artifact actions, control and work share one bounded allowance."""

from unittest.mock import AsyncMock, patch

import pytest

from dialectica import Workflow
from dialectica.agent_runtime import AgentResponse, TokenUsage
from examples.patterns.meta_reasoning_pattern import (
    Action,
    Assessment,
    Evaluation,
    Proposals,
    create_meta_reasoning_engine,
)


async def test_one_call_budget_returns_stored_seed_without_extra_synthesis():
    mocked = AsyncMock(return_value="seed answer")
    with patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked):
        result = await create_meta_reasoning_engine("facts", max_calls=1).run()
    assert result["final_answer"] == "seed answer"
    assert result["selected_id"] == "artifact-0"
    assert result["forced_stop"]
    assert mocked.await_count == 1


async def test_direct_stop_selects_earlier_artifact_and_worker_context_is_selective():
    mocked = AsyncMock(
        side_effect=[
            "seed answer",
            Action(
                kind="run", instruction="check carefully", context_ids=["artifact-0"]
            ),
            "revision answer",
            Action(kind="stop", artifact_id="artifact-0"),
        ]
    )
    with patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked):
        result = await create_meta_reasoning_engine(
            "facts", mode="direct", max_calls=4
        ).run()
    assert result["final_answer"] == "seed answer"
    assert result["artifacts"][1]["parents"] == ["artifact-0"]
    worker_prompt = mocked.await_args_list[2].args[0]
    assert "seed answer" in worker_prompt
    assert "check carefully" in worker_prompt
    assert mocked.await_args_list[2].kwargs["sees"] == []


async def test_staged_control_charges_four_stages_and_preserves_private_state():
    action = Action(kind="run", instruction="revise", context_ids=["artifact-0"])
    mocked = AsyncMock(
        side_effect=[
            "seed",
            Assessment(state="PRIVATE ASSESSMENT"),
            Proposals(options=[action]),
            Evaluation(option=0, rationale="worth checking"),
            action,
            "revised",
        ]
    )
    with patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked):
        result = await create_meta_reasoning_engine("facts", max_calls=6).run()
    assert mocked.await_count == 6
    assert result["controller_calls"] == 4 and result["worker_calls"] == 2
    assert "PRIVATE ASSESSMENT" not in mocked.await_args_list[-1].args[0]
    assert "remaining" not in mocked.await_args_list[2].args[0].lower()


async def test_unknown_artifact_is_rejected_before_worker_dispatch():
    mocked = AsyncMock(
        side_effect=[
            "seed",
            Action(kind="run", instruction="go", context_ids=["missing"]),
        ]
    )
    with (
        patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked),
        pytest.raises(ValueError, match="unknown artifact"),
    ):
        await create_meta_reasoning_engine("facts", mode="direct", max_calls=4).run()
    assert mocked.await_count == 2


async def test_joined_parent_budget_cannot_be_bypassed():
    transport = AsyncMock(
        return_value=AgentResponse("seed", TokenUsage(total_tokens=10))
    )

    async def script():
        return await create_meta_reasoning_engine("facts", max_calls=20).run()

    with patch("dialectica.agent_runtime.run_agent", transport):
        result = await Workflow(script, budget_total=1).run()
    assert result["final_answer"] == "seed"
    assert transport.await_count == 1


def test_invalid_action_contracts_are_rejected():
    with pytest.raises(ValueError):
        Action(kind="stop")
    with pytest.raises(ValueError):
        Action(kind="run", artifact_id="artifact-0", instruction="go")
    with pytest.raises(ValueError):
        create_meta_reasoning_engine("facts", max_calls=0)


async def test_unaffordable_dispatched_work_is_marked_as_not_executed():
    mocked = AsyncMock(side_effect=["seed", Action(kind="run", instruction="revise")])
    with patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked):
        result = await create_meta_reasoning_engine(
            "facts", mode="direct", max_calls=2
        ).run()
    assert result["history"][0]["status"] == "skipped_budget"
    assert len(result["artifacts"]) == 1


async def test_dispatch_cannot_change_the_evaluated_worker_assignment():
    proposal = Action(kind="run", instruction="check", worker_index=0)
    dispatch = Action(kind="run", instruction="check", worker_index=1)
    mocked = AsyncMock(
        side_effect=[
            "seed",
            Assessment(state="needs work"),
            Proposals(options=[proposal]),
            Evaluation(option=0, rationale="use worker zero"),
            dispatch,
        ]
    )
    with (
        patch("examples.patterns.meta_reasoning_pattern.wf.agent", mocked),
        pytest.raises(ValueError, match="chosen proposal"),
    ):
        await create_meta_reasoning_engine(
            "facts", workers=["google:a", "google:b"], max_calls=6
        ).run()
    assert mocked.await_count == 5
