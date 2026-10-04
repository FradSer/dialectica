"""Unit tests for the model-config factory (no network)."""

import pytest
from google.adk.models.lite_llm import LiteLlm

from dialectica.llm_config import _DEFAULT_MODEL, get_model_config


def test_google_provider_returns_bare_model_name(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "google:gemini-3.5-flash")
    assert get_model_config() == "gemini-3.5-flash"


def test_missing_config_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DEFAULT_MODEL_CONFIG", raising=False)
    assert get_model_config() == _DEFAULT_MODEL


def test_malformed_explicit_config_is_rejected(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "no-colon-here")
    with pytest.raises(ValueError, match="provider:model"):
        get_model_config()


def test_unknown_explicit_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "mystery:model-x")
    with pytest.raises(ValueError, match="provider"):
        get_model_config()


def test_role_override_beats_default(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "google:gemini-3.5-flash")
    monkeypatch.setenv("JUDGE_MODEL_CONFIG", "google:gemini-3.1-pro-preview")
    assert get_model_config("Judge") == "gemini-3.1-pro-preview"


def test_openai_provider_builds_litellm_when_credentialed(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "openai:qwen3.6-35b-a3b")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_BASE", "http://example/v1")
    config = get_model_config()
    assert isinstance(config, LiteLlm)
    assert config.model == "openai/qwen3.6-35b-a3b"


def test_openai_provider_without_credentials_is_rejected(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "openai:gpt-4o")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API"):
        get_model_config()


def test_openrouter_without_key_is_rejected(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "openrouter:some/model")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        get_model_config()


def test_openrouter_model_routes_through_openrouter(monkeypatch):
    from litellm import get_llm_provider

    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "openrouter:anthropic/claude-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-placeholder")
    config = get_model_config()
    assert config.model == "openrouter/anthropic/claude-test"
    assert get_llm_provider(config.model)[1] == "openrouter"


@pytest.mark.parametrize("config", ["", "google:", "openai:   "])
def test_empty_explicit_config_or_model_is_rejected(monkeypatch, config):
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", config)
    with pytest.raises(ValueError):
        get_model_config()


def test_empty_role_override_is_not_silently_ignored(monkeypatch):
    monkeypatch.setenv("GENERATOR_MODEL_CONFIG", "")
    monkeypatch.setenv("DEFAULT_MODEL_CONFIG", "google:default")
    with pytest.raises(ValueError, match="provider:model"):
        get_model_config("Generator")


async def test_empty_workflow_model_is_not_an_unspecified_model():
    from unittest.mock import AsyncMock, patch

    from dialectica import Workflow, agent

    with (
        patch(
            "dialectica.agent_runtime.run_agent",
            AsyncMock(return_value="unexpected fallback"),
        ),
        pytest.raises(ValueError, match="provider:model"),
    ):
        await Workflow(lambda: agent("do not dispatch", model="")).run()


def test_empty_factory_model_is_not_an_unspecified_model():
    from dialectica.agent_factory import create_agent

    with pytest.raises(ValueError, match="nonempty"):
        create_agent("Generator", model_config="")
