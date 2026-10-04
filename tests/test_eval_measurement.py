"""Given concurrent experiment arms, cost and failures stay assigned to each arm."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from dialectica import agent_runtime
from dialectica.agent_runtime import AgentResponse, TokenUsage
from evals.measurement import measure_arm, observe_runtime


async def test_concurrent_arm_usage_is_isolated():
    async def real_call(agent, instruction, **kwargs):
        await asyncio.sleep(0)
        return AgentResponse(instruction, TokenUsage(total_tokens=int(instruction)))

    async def run(value):
        return await agent_runtime.run_agent(None, str(value))

    with patch("dialectica.agent_runtime.run_agent", real_call), observe_runtime():
        first, second = await asyncio.gather(
            measure_arm("first", lambda: run(15)),
            measure_arm("second", lambda: run(30)),
        )
    assert first.usage.total_tokens == 15
    assert second.usage.total_tokens == 30
    assert first.calls == second.calls == 1
    assert first.output == "15"
    assert second.output == "30"
    assert first.seconds >= 0
    assert first.records[0]["prompt"] == "15"
    assert first.records[0]["raw_output"] == "15"
    assert first.records[0]["usage"]["total_tokens"] == 15
    assert second.records[0]["prompt"] == "30"


async def test_failed_arm_preserves_usage_and_returns_failure_receipt():
    async def failed(agent, instruction, **kwargs):
        error = ConnectionError("failed")
        error.dialectica_usage = TokenUsage(total_tokens=15, unknown_calls=1)
        raise error

    async def run():
        return await agent_runtime.run_agent(None, "go", max_attempts=1)

    with patch("dialectica.agent_runtime.run_agent", failed), observe_runtime():
        receipt = await measure_arm("failed", run)
    assert receipt.error == "ConnectionError"
    assert receipt.output is None
    assert receipt.failures == 1
    assert receipt.usage.total_tokens == 15
    assert receipt.usage.unknown_calls == 1
    assert receipt.records[0]["error"] == "ConnectionError"
    assert receipt.records[0]["raw_output"] is None
    assert receipt.records[0]["usage"]["unknown_calls"] == 1


async def test_cancellation_propagates_from_measurement():
    async def cancelled():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await measure_arm("cancelled", cancelled)


async def test_detached_late_task_cannot_mutate_a_finished_receipt():
    gate = asyncio.Event()
    tasks = []
    transport = AsyncMock(
        return_value=AgentResponse("late", TokenUsage(total_tokens=15))
    )

    async def arm():
        async def late():
            await gate.wait()
            return await agent_runtime.run_agent(None, "late")

        tasks.append(asyncio.create_task(late()))
        return "done"

    with patch("dialectica.agent_runtime.run_agent", transport), observe_runtime():
        receipt = await measure_arm("detached", arm)
        snapshot = receipt.to_dict()
        gate.set()
        with pytest.raises(RuntimeError, match="finished"):
            await tasks[0]
        assert receipt.to_dict() == snapshot
        transport.assert_not_awaited()


async def test_unjoined_inflight_call_is_drained_and_invalidates_arm():
    started = asyncio.Event()
    tasks = []

    async def transport(agent, instruction, **kwargs):
        started.set()
        await asyncio.Event().wait()

    async def arm():
        tasks.append(asyncio.create_task(agent_runtime.run_agent(None, "go")))
        await started.wait()
        return "premature result"

    with patch("dialectica.agent_runtime.run_agent", transport), observe_runtime():
        receipt = await measure_arm("unjoined", arm)
        snapshot = receipt.to_dict()
        assert receipt.error == "UnjoinedArmCalls"
        assert receipt.output is None
        assert receipt.calls == receipt.failures == 1
        assert receipt.usage.unknown_calls == 1
        assert tasks[0].cancelled()
        assert receipt.to_dict() == snapshot
