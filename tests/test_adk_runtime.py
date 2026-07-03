"""Unit tests for ADK 2.3 runtime wiring (context cache, telemetry)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.context_cache_config import ContextCacheConfig

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

    assert captured["agent"] is agent
    assert "app" not in captured


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

    with (
        patch("dialectica.agent_runtime.ensure_otel_setup") as otel,
        patch("dialectica.agent_runtime._make_runner", return_value=fake_runner),
    ):
        import asyncio

        from dialectica.agent_runtime import _call_agent_once

        asyncio.run(_call_agent_once(agent, "go"))
        otel.assert_called_once()
