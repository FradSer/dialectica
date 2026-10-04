"""Given live completion order or cached producers, resume preserves the contract."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from litellm import AuthenticationError, NotFoundError, RateLimitError

from dialectica import agent_runtime
from dialectica import workflow as wf
from dialectica.agent_runtime import AgentResponse, TokenUsage
from dialectica.workflow import Workflow
from dialectica.workflow_journal import RunJournal


async def test_out_of_order_parallel_resume_reuses_every_result(tmp_path):
    holder = {}
    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        await asyncio.sleep(0.01 if instruction == "first" else 0)
        return AgentResponse(instruction, TokenUsage(total_tokens=123))

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [lambda: wf.agent("first"), lambda: wf.agent("second")]
        )

    with patch("dialectica.agent_runtime.run_agent", fake):
        assert await Workflow(script, journal_dir=tmp_path).run() == ["first", "second"]
        journal = RunJournal.load(holder["id"], tmp_path)
        assert [e.sequence for e in journal.entries] == [0, 1]
        assert sum(e.usage.total_tokens for e in journal.entries) == 246
        calls.clear()
        assert await Workflow(
            script, journal_dir=tmp_path, resume_run_id=holder["id"]
        ).run() == ["first", "second"]
        assert calls == []


async def test_cached_producer_restores_context_and_changed_tail(tmp_path):
    holder = {}
    calls = []
    changed = False

    async def fake(agent, instruction):
        calls.append(instruction)
        return "shared-value-731"

    async def script():
        holder["id"] = wf.run_id()
        await wf.agent("produce", label="producer")
        return await wf.agent("changed" if changed else "consume", sees=["producer"])

    with patch("dialectica.agent_runtime.run_agent", fake):
        await Workflow(script, journal_dir=tmp_path).run()
        changed = True
        calls.clear()
        await Workflow(script, journal_dir=tmp_path, resume_run_id=holder["id"]).run()
        assert len(calls) == 1
        assert "shared-value-731" in calls[0]
        calls.clear()
        await Workflow(script, journal_dir=tmp_path, resume_run_id=holder["id"]).run()
        assert calls == []
        assert len(RunJournal.load(holder["id"], tmp_path).entries) == 2


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError("invalid key", "openai", "test"),
        NotFoundError("retired model", "openai", "test"),
        RateLimitError("Coding Plan expired error 1309", "openai", "test"),
        RateLimitError("您的GLM Coding Plan套餐已到期，暂无法使用", "openai", "test"),
        RateLimitError("insufficient_quota", "openai", "test"),
    ],
)
async def test_permanent_provider_failure_is_not_retried(error):
    call = AsyncMock(side_effect=error)
    sleep = AsyncMock()
    with (
        patch.object(agent_runtime, "_call_agent_once", call),
        patch.object(agent_runtime.asyncio, "sleep", sleep),
        pytest.raises(type(error)),
    ):
        await agent_runtime.run_agent(object(), "test")
    assert call.await_count == 1
    sleep.assert_not_awaited()


async def test_structured_reasks_record_all_successful_call_usage(tmp_path):
    from pydantic import BaseModel

    class Answer(BaseModel):
        value: int

    holder = {}
    responses = iter(["invalid", '{"value": 731}'])

    async def fake(agent, instruction):
        return AgentResponse(next(responses), TokenUsage(total_tokens=123))

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("produce", schema=Answer)

    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await Workflow(script, journal_dir=tmp_path).run()
    assert result.value == 731
    assert RunJournal.load(holder["id"], tmp_path).entries[0].usage.total_tokens == 246


async def test_legacy_duplicate_positions_are_recomputed(tmp_path):
    holder = {}
    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        return instruction

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [lambda: wf.agent("first"), lambda: wf.agent("second")]
        )

    with patch("dialectica.agent_runtime.run_agent", fake):
        await Workflow(script, journal_dir=tmp_path).run()
        journal = RunJournal.load(holder["id"], tmp_path)
        journal.entries[1].sequence = 0
        journal.persist(tmp_path / holder["id"] / "journal.jsonl")
        calls.clear()
        assert await Workflow(
            script, journal_dir=tmp_path, resume_run_id=holder["id"]
        ).run() == ["first", "second"]
        assert calls == ["first", "second"]
        assert [
            entry.sequence for entry in RunJournal.load(holder["id"], tmp_path).entries
        ] == [0, 1]


async def test_payment_required_status_without_billing_text_is_not_retried():
    class PaymentRequired(Exception):
        status_code = 402

    call = AsyncMock(side_effect=PaymentRequired("Request rejected"))
    sleep = AsyncMock()
    with (
        patch.object(agent_runtime, "_call_agent_once", call),
        patch.object(agent_runtime.asyncio, "sleep", sleep),
        pytest.raises(PaymentRequired),
    ):
        await agent_runtime.run_agent(object(), "test")
    assert call.await_count == 1
    sleep.assert_not_awaited()
