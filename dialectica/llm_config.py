"""Dynamic LLM configuration factory for ADK 2.0.

Reads DEFAULT_MODEL_CONFIG from environment (provider:model_name format).
Provides a factory to create model configs for dynamically spawned agents.
"""

import logging
import os
from typing import Any

from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-3.5-flash"


def _log_credential_warnings(model_name: str) -> None:
    """Log warnings if required Google credentials are missing."""
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
    if use_vertex:
        if not os.environ.get("GOOGLE_CLOUD_PROJECT") or not os.environ.get(
            "GOOGLE_CLOUD_LOCATION"
        ):
            logger.warning(
                "Using Vertex AI with '%s', but GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION not set.",
                model_name,
            )
    else:
        if not os.environ.get("GOOGLE_API_KEY"):
            logger.warning(
                "Using Google AI Studio with '%s', but GOOGLE_API_KEY not set.",
                model_name,
            )


def _parse_model_config(config_str: str) -> str | LiteLlm:
    """Resolve an explicit provider:model without silently changing models.

    An absent DEFAULT_MODEL_CONFIG uses the native default in get_model_config.
    Invalid explicit configuration or unavailable provider credentials fail
    before dispatch, preventing mislabeled experimental arms.
    """
    if not config_str or ":" not in config_str:
        raise ValueError("Model configuration must use provider:model format")
    provider, model_name = config_str.strip().split(":", 1)
    provider, model_name = provider.strip().lower(), model_name.strip()
    if not model_name:
        raise ValueError("Model configuration requires a nonempty model name")
    if provider == "google":
        _log_credential_warnings(model_name)
        return model_name
    if provider == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise ValueError("OpenRouter requires OPENROUTER_API_KEY")
        routed_model = (
            model_name
            if model_name.startswith("openrouter/")
            else f"openrouter/{model_name}"
        )
        return LiteLlm(model=routed_model)
    if provider == "openai":
        api_base = os.environ.get("OPENAI_API_BASE")
        if not os.environ.get("OPENAI_API_KEY") or not api_base:
            raise ValueError(
                "OpenAI-compatible models require OPENAI_API_KEY and OPENAI_API_BASE"
            )
        kwargs: dict[str, Any] = {"api_base": api_base}
        if os.environ.get("DIALECTICA_DISABLE_THINKING", "").lower() == "true":
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        return LiteLlm(model=f"openai/{model_name}", **kwargs)
    raise ValueError("Unsupported model provider: use google, openrouter or openai")


def get_model_config(role: str | None = None) -> str | LiteLlm:
    """Get model config for a role, with optional role-specific env override.

    Checks {ROLE}_MODEL_CONFIG first, then DEFAULT_MODEL_CONFIG.
    Falls back to gemini-3.5-flash if neither is set.
    """
    if role:
        role_override = os.environ.get(f"{role.upper()}_MODEL_CONFIG")
        if role_override is not None:
            logger.info("Role-specific config for '%s': %s", role, role_override)
            return _parse_model_config(role_override)

    default_str = os.environ.get("DEFAULT_MODEL_CONFIG", f"google:{_DEFAULT_MODEL}")
    return _parse_model_config(default_str)
