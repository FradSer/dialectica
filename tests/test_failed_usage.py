"""Given a billable model turn, later failure must not erase its reported usage."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from dialectica import agent_runtime
from dialectica import workflow as wf
from dialectica.agent_factory import create_agent
from dialectica.workflow import Workflow
from dialectica.workflow_journal import RunJournal


class BillableToolModel(BaseLlm):
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(name="lookup", args={})],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15
            ),
        )


async def test_failed_tool_turn_is_metered_and_journaled(tmp_path):
    holder = {}

    def lookup() -> int:
        raise ValueError("tool rejected input")

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("lookup", tools=[lookup])

    with (
        patch(
            "dialectica.workflow.get_model_config",
            return_value=BillableToolModel(model="offline"),
        ),
        pytest.raises(ValueError) as caught,
    ):
        await Workflow(script, journal_dir=tmp_path).run()
    assert caught.value.dialectica_usage.total_tokens == 45
    journal = RunJournal.load(holder["id"], tmp_path)
    assert journal.entries[0].result_kind == "error"
    assert journal.entries[0].usage.total_tokens == 45
    assert journal.lookup(0, journal.entries[0].cache_key) is None


async def test_failure_before_response_reports_unknown_usage():
    class UnavailableModel(BaseLlm):
        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            raise ConnectionError("connection lost")
            yield

    agent = create_agent("Generator", model_config=UnavailableModel(model="offline"))
    with pytest.raises(ConnectionError) as caught:
        await agent_runtime.run_agent(agent, "go", max_attempts=1)
    assert caught.value.dialectica_usage.unknown_calls == 1
    assert caught.value.dialectica_usage.total_tokens == 0


async def test_response_callback_failure_before_event_keeps_usage():
    def after_model(callback_context, llm_response):
        raise ValueError("response processing failed before event")

    agent = create_agent("Generator", model_config=BillableToolModel(model="offline"))
    agent.after_model_callback = after_model
    with pytest.raises(ValueError) as caught:
        await agent_runtime.run_agent(agent, "go", max_attempts=1)
    assert caught.value.dialectica_usage.total_tokens == 15
    assert caught.value.dialectica_usage.unknown_calls == 0


async def test_failed_receipt_survives_resume_replacing_error_entry(tmp_path):
    import json

    from dialectica.agent_runtime import TokenUsage

    holder = {}
    failed = True

    async def fake(agent, instruction):
        if failed:
            error = ConnectionError("failed")
            error.dialectica_usage = TokenUsage(total_tokens=15, unknown_calls=1)
            raise error
        return agent_runtime.AgentResponse("ok", TokenUsage(total_tokens=30))

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("go")

    with patch("dialectica.agent_runtime.run_agent", fake):
        with pytest.raises(ConnectionError):
            await Workflow(script, journal_dir=tmp_path).run()
        failed = False
        assert (
            await Workflow(
                script, journal_dir=tmp_path, resume_run_id=holder["id"]
            ).run()
            == "ok"
        )
        receipts = [
            json.loads(line)
            for line in (tmp_path / holder["id"] / "usage.jsonl")
            .read_text()
            .splitlines()
        ]
        assert [r["failed"] for r in receipts] == [True, False]
        assert sum(r["usage"]["total_tokens"] for r in receipts) == 45
        assert sum(r["usage"]["unknown_calls"] for r in receipts) == 1
        assert (
            await Workflow(
                script, journal_dir=tmp_path, resume_run_id=holder["id"]
            ).run()
            == "ok"
        )
        assert (
            len((tmp_path / holder["id"] / "usage.jsonl").read_text().splitlines()) == 2
        )


async def test_cancellation_during_retry_delay_keeps_prior_usage():
    import asyncio
    from unittest.mock import AsyncMock

    from dialectica.agent_runtime import TokenUsage

    error = ConnectionError("failed after reported usage")
    error.dialectica_usage = TokenUsage(total_tokens=15)
    with (
        patch(
            "dialectica.agent_runtime._call_agent_once", AsyncMock(side_effect=error)
        ),
        patch(
            "dialectica.agent_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        pytest.raises(asyncio.CancelledError) as caught,
    ):
        await agent_runtime.run_agent(object(), "go")
    assert caught.value.dialectica_usage.total_tokens == 15


@pytest.mark.parametrize("fail", [True, False])
async def test_partial_usage_survives_failure_without_double_counting_final(fail):
    class PartialModel(BaseLlm):
        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            yield LlmResponse(
                partial=True,
                content=types.Content(role="model", parts=[types.Part(text="RE")]),
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=10,
                    candidates_token_count=5,
                    total_token_count=15,
                ),
            )
            if fail:
                raise ConnectionError("stream interrupted")
            yield LlmResponse(
                partial=False,
                content=types.Content(role="model", parts=[types.Part(text="READY")]),
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=10,
                    candidates_token_count=10,
                    total_token_count=20,
                ),
            )

    agent = create_agent("Generator", model_config=PartialModel(model="offline"))
    if fail:
        with pytest.raises(ConnectionError) as caught:
            await agent_runtime.run_agent(agent, "go", max_attempts=1)
        assert caught.value.dialectica_usage.total_tokens == 15
        assert caught.value.dialectica_usage.unknown_calls == 1
    else:
        response = await agent_runtime.run_agent(agent, "go", max_attempts=1)
        assert response.usage.total_tokens == 20
        assert response.usage.unknown_calls == 0


async def test_before_model_cached_response_keeps_reported_usage():
    def cached_response(callback_context, llm_request):
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="cached")]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=1, candidates_token_count=1, total_token_count=2
            ),
        )

    agent = create_agent("Generator", model_config=BillableToolModel(model="offline"))
    agent.before_model_callback = cached_response
    response = await agent_runtime.run_agent(agent, "go", max_attempts=1)
    assert str(response) == "cached"
    assert response.usage.total_tokens == 2
    assert response.usage.unknown_calls == 0


async def test_same_agent_concurrent_callbacks_have_distinct_usage_slots():
    from types import SimpleNamespace

    from google.adk.events import EventActions

    from dialectica.agent_runtime import _active_usage, _UsagePlugin, _UsageTracker

    tracker = _UsageTracker()
    token = _active_usage.set(tracker)
    try:
        plugin = _UsagePlugin()
        contexts = [
            SimpleNamespace(
                invocation_id="same", agent_name="same", actions=EventActions()
            )
            for _ in range(2)
        ]
        for context in contexts:
            await plugin.before_model_callback(
                callback_context=context, llm_request=None
            )
        for context, total in zip(contexts, [15, 20], strict=True):
            await plugin.after_model_callback(
                callback_context=context,
                llm_response=LlmResponse(
                    usage_metadata=types.GenerateContentResponseUsageMetadata(
                        total_token_count=total
                    )
                ),
            )
        assert tracker.usage().total_tokens == 35
        assert tracker.usage().unknown_calls == 0
    finally:
        _active_usage.reset(token)


async def test_cached_response_usage_survives_later_tool_failure():
    def lookup() -> int:
        raise ValueError("failed after cached response")

    def cached_response(callback_context, llm_request):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(name="lookup", args={})],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                total_token_count=2
            ),
        )

    agent = create_agent(
        "Generator", model_config=BillableToolModel(model="offline"), tools=[lookup]
    )
    agent.before_model_callback = cached_response
    with pytest.raises(ValueError) as caught:
        await agent_runtime.run_agent(agent, "go", max_attempts=1)
    assert caught.value.dialectica_usage.total_tokens == 2
    assert caught.value.dialectica_usage.unknown_calls == 0
