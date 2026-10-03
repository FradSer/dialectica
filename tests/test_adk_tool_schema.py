"""Offline integration tests through the real ADK runner and tool loop."""

import asyncio
from collections.abc import AsyncGenerator
from threading import get_ident
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.models import BaseLlm, LlmCapabilities, LlmRequest, LlmResponse
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from pydantic import BaseModel, PrivateAttr

from dialectica import TokenUsage, Workflow
from dialectica import workflow as wf
from dialectica.agent_factory import create_agent
from dialectica.agent_runtime import _make_runner, run_agent


class Answer(BaseModel):
    value: int


class ToolSchemaModel(BaseLlm):
    native: bool
    _turns: int = PrivateAttr(default=0)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=self.native)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._turns += 1
        assert (llm_request.config.response_schema is not None) == self.native
        if self._turns == 1:
            part = types.Part.from_function_call(name="lookup", args={})
        else:
            results = [
                p.function_response.response
                for content in llm_request.contents
                for p in content.parts or []
                if p.function_response and p.function_response.name == "lookup"
            ]
            assert results == [{"value": 42}]
            if self.native:
                part = types.Part.from_text(text='{"value": 42}')
            else:
                part = types.Part.from_function_call(
                    name="set_model_response", args={"value": 42}
                )
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15
            ),
        )


@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize("workers", [None, "2"])
async def test_tool_schema_uses_native_or_fallback_and_honors_workers(
    monkeypatch, native, workers
):
    """Given either capability, tool results become validated structured output.

    When workers are enabled, the real sync tool runs off the event loop;
    otherwise it keeps the caller's thread. Both model turns are metered.
    """
    monkeypatch.delenv("DIALECTICA_CONTEXT_CACHE", raising=False)
    monkeypatch.delenv("DIALECTICA_MAX_LLM_CALLS", raising=False)
    if workers is None:
        monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    else:
        monkeypatch.setenv("DIALECTICA_TOOL_WORKERS", workers)
    tool_threads = []
    caller_thread = get_ident()

    def lookup() -> dict[str, int]:
        tool_threads.append(get_ident())
        return {"value": 42}

    model = ToolSchemaModel(model="offline", native=native)

    async def script() -> tuple[Answer, TokenUsage]:
        answer = await wf.agent("Look up the value", schema=Answer, tools=[lookup])
        return answer, wf.budget().usage()

    run = Workflow(script)
    with patch("dialectica.workflow.get_model_config", return_value=model):
        result, usage = await run.run()
    assert result == Answer(value=42)
    assert len(tool_threads) == 1
    assert (tool_threads[0] != caller_thread) == (workers is not None)
    assert usage.total_tokens == 30


class ToolLoopModel(BaseLlm):
    _turns: int = PrivateAttr(default=0)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._turns += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(name="lookup", args={})],
            )
        )


async def test_real_tool_loop_stops_at_call_limit_without_retry(monkeypatch):
    """Given a looping model, its ADK limit stops further tool side effects."""
    monkeypatch.setenv("DIALECTICA_MAX_LLM_CALLS", "2")
    monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    calls = []

    def lookup() -> int:
        calls.append(1)
        return 42

    model = ToolLoopModel(model="offline")
    agent = create_agent("Generator", tools=[lookup], model_config=model)
    with pytest.raises(LlmCallsLimitExceededError):
        await run_agent(agent, "go", base_delay=0)
    assert model._turns == 2
    assert len(calls) == 2


async def test_real_inflight_async_tool_is_cancelled_and_runner_closes(monkeypatch):
    """When the caller cancels, ADK stops the async tool and releases resources."""
    monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    entered = asyncio.Event()
    stopped = asyncio.Event()

    async def lookup() -> int:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return 42

    model = ToolLoopModel(model="offline")
    agent = create_agent("Generator", tools=[lookup], model_config=model)
    runner = _make_runner(agent)
    with (
        patch("dialectica.agent_runtime._make_runner", return_value=runner),
        patch.object(
            runner, "close", new_callable=AsyncMock, wraps=runner.close
        ) as close,
    ):
        task = asyncio.create_task(run_agent(agent, "go"))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert stopped.is_set()
        close.assert_awaited_once()
    assert model._turns == 1


async def test_retry_keeps_toolset_open_and_uses_fresh_session(monkeypatch):
    """A failed attempt must not close tools or leak history into its retry."""
    monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    calls = []

    def lookup() -> dict[str, int]:
        calls.append(1)
        return {"value": 42}

    class ClosingToolset(BaseToolset):
        closed = False
        closes = 0

        async def get_tools(self, readonly_context=None):
            assert not self.closed, "retry reused a closed toolset"
            return [FunctionTool(lookup)]

        async def close(self):
            self.closed = True
            self.closes += 1

    class FailingModel(ToolSchemaModel):
        _failed: bool = PrivateAttr(default=False)

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            if self._turns == 1 and not self._failed:
                self._failed = True
                self._turns = 0
                raise ConnectionError("transient transport failure")
            if self._turns == 0:
                assert len(llm_request.contents) == 1
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    model = FailingModel(model="offline", native=True)
    toolset = ClosingToolset()
    agent = create_agent(
        "Generator", tools=[toolset], model_config=model, output_schema=Answer
    )
    response = await run_agent(agent, "go", base_delay=0)
    assert Answer.model_validate_json(response) == Answer(value=42)
    assert len(calls) == 2
    assert response.usage.total_tokens == 45
    assert response.usage.unknown_calls == 1
    assert toolset.closed
    assert toolset.closes == 1
