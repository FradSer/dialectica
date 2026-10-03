"""Unit tests for ADK runtime configuration and invocation lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError

from dialectica import adk_config
from dialectica.agent_runtime import _make_runner, _reset_adk_runtime_state


@pytest.fixture(autouse=True)
def reset_adk_state():
    _reset_adk_runtime_state()
    adk_config.reset_adk_config_state()
    yield
    _reset_adk_runtime_state()
    adk_config.reset_adk_config_state()


def test_context_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DIALECTICA_CONTEXT_CACHE", raising=False)
    assert adk_config.get_context_cache_config() is None


def test_context_cache_enabled_from_env(monkeypatch):
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE", "true")
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_INTERVALS", "5")
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_TTL_SECONDS", "600")
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_MIN_TOKENS", "8192")
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_CREATE_TIMEOUT_MS", "5000")

    cfg = adk_config.get_context_cache_config()
    assert isinstance(cfg, ContextCacheConfig)
    assert cfg.cache_intervals == 5
    assert cfg.ttl_seconds == 600
    assert cfg.min_tokens == 8192
    assert cfg.create_http_options is not None
    assert cfg.create_http_options.timeout == 5000


def test_invalid_cache_config_can_be_corrected(monkeypatch):
    """Given invalid env, failure must not poison subsequent configuration."""
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE", "true")
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_INTERVALS", "invalid")
    with pytest.raises(ValueError):
        adk_config.get_context_cache_config()
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE_INTERVALS", "5")
    assert adk_config.get_context_cache_config().cache_intervals == 5


@pytest.mark.parametrize(
    "failure", [None, RuntimeError("failed"), asyncio.CancelledError()]
)
async def test_runner_closes_after_success_failure_or_cancellation(failure):
    """When a call ends by any path, its runner releases owned resources."""
    from dialectica.agent_runtime import _call_agent_once

    runner = MagicMock()
    runner.run_debug = AsyncMock(return_value=[], side_effect=failure)
    runner.close = AsyncMock()
    with patch("dialectica.agent_runtime._make_runner", return_value=runner):
        if failure is None:
            await _call_agent_once(LlmAgent(name="test"), "go")
        else:
            with pytest.raises(type(failure)):
                await _call_agent_once(LlmAgent(name="test"), "go")
    runner.close.assert_awaited_once()


def test_run_config_enables_bounded_sync_tool_workers(monkeypatch):
    """Given worker and call limits, pass validated native config to ADK."""
    monkeypatch.setenv("DIALECTICA_TOOL_WORKERS", "2")
    monkeypatch.setenv("DIALECTICA_MAX_LLM_CALLS", "12")
    cfg = adk_config.get_run_config()
    assert cfg.tool_thread_pool_config.max_workers == 2
    assert cfg.max_llm_calls == 12


def test_run_config_defaults_preserve_adk_behavior(monkeypatch):
    monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    monkeypatch.delenv("DIALECTICA_MAX_LLM_CALLS", raising=False)
    monkeypatch.delenv("ADK_MAX_LLM_CALLS", raising=False)
    cfg = adk_config.get_run_config()
    assert cfg.tool_thread_pool_config is None
    assert cfg.max_llm_calls == 500


def test_run_config_preserves_native_adk_limit_unless_overridden(monkeypatch):
    monkeypatch.setenv("ADK_MAX_LLM_CALLS", "7")
    monkeypatch.delenv("DIALECTICA_MAX_LLM_CALLS", raising=False)
    assert adk_config.get_run_config().max_llm_calls == 7
    monkeypatch.setenv("DIALECTICA_MAX_LLM_CALLS", "12")
    assert adk_config.get_run_config().max_llm_calls == 12


@pytest.mark.parametrize(
    "name", ["DIALECTICA_TOOL_WORKERS", "DIALECTICA_MAX_LLM_CALLS"]
)
@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_run_config_rejects_invalid_limits(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        adk_config.get_run_config()


async def test_llm_call_limit_is_not_retried():
    """When ADK exhausts its call limit, retry must not restart the tool loop."""
    from dialectica.agent_runtime import run_agent

    with (
        patch(
            "dialectica.agent_runtime._call_agent_once",
            new_callable=AsyncMock,
            side_effect=LlmCallsLimitExceededError("limit reached"),
        ) as call,
        pytest.raises(LlmCallsLimitExceededError),
    ):
        await run_agent(LlmAgent(name="test"), "go", base_delay=0)
    call.assert_awaited_once()


def test_make_runner_uses_app_when_context_cache_enabled(monkeypatch):
    monkeypatch.setenv("DIALECTICA_CONTEXT_CACHE", "1")
    agent = LlmAgent(name="t", instruction="hi", model="gemini-3.5-flash")

    captured: dict = {}

    class FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with patch("dialectica.agent_runtime.InMemoryRunner", FakeRunner):
        _make_runner(agent)

    app = captured["app"]
    assert app.name == "dialectica"
    assert app.root_agent is agent
    assert app.context_cache_config is not None
    assert captured["app_name"] == "dialectica"
    assert "agent" not in captured


def test_make_runner_plain_when_cache_disabled(monkeypatch):
    monkeypatch.delenv("DIALECTICA_CONTEXT_CACHE", raising=False)
    agent = LlmAgent(name="t", instruction="hi", model="gemini-3.5-flash")

    captured: dict = {}

    class FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with patch("dialectica.agent_runtime.InMemoryRunner", FakeRunner):
        _make_runner(agent)

    assert captured["app"].root_agent is agent
    assert captured["app"].context_cache_config is None
    assert captured["app"].plugins


def test_ensure_otel_when_flag_set(monkeypatch):
    monkeypatch.setenv("DIALECTICA_ADK_TELEMETRY", "true")
    with patch("google.adk.telemetry.setup.maybe_set_otel_providers") as setup_otel:
        adk_config.ensure_otel_setup()
        setup_otel.assert_called_once()
        adk_config.ensure_otel_setup()
        setup_otel.assert_called_once()


def test_ensure_otel_when_otlp_endpoint_set(monkeypatch):
    monkeypatch.delenv("DIALECTICA_ADK_TELEMETRY", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    with patch("google.adk.telemetry.setup.maybe_set_otel_providers") as setup_otel:
        adk_config.ensure_otel_setup()
        setup_otel.assert_called_once()


def test_call_agent_once_invokes_otel_setup(monkeypatch):
    monkeypatch.delenv("DIALECTICA_CONTEXT_CACHE", raising=False)
    agent = LlmAgent(name="t", instruction="hi", model="gemini-3.5-flash")
    fake_runner = MagicMock()
    fake_runner.run_debug = AsyncMock(return_value=[])
    fake_runner.close = AsyncMock()

    with (
        patch("dialectica.agent_runtime.ensure_otel_setup") as otel,
        patch("dialectica.agent_runtime._make_runner", return_value=fake_runner),
    ):
        import asyncio

        from dialectica.agent_runtime import _call_agent_once

        asyncio.run(_call_agent_once(agent, "go"))
        otel.assert_called_once()
