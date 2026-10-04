"""Nested reflection must charge all stages to the caller's shared allowance."""

from unittest.mock import AsyncMock, patch

import pytest

from dialectica import BudgetExhausted, Workflow
from dialectica.agent_runtime import AgentResponse, TokenUsage
from examples.patterns.reflection_pattern import create_reflection_engine


async def test_reflection_cannot_open_an_unbudgeted_run_inside_a_parent():
    transport = AsyncMock(
        return_value=AgentResponse("analysis", TokenUsage(total_tokens=10))
    )

    async def script():
        return await create_reflection_engine("facts", roster=["google:test"]).run()

    with (
        patch("dialectica.agent_runtime.run_agent", transport),
        pytest.raises(BudgetExhausted),
    ):
        await Workflow(script, budget_total=3).run()
    assert transport.await_count == 3
