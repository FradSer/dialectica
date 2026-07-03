"""ADK 2.3+ runtime configuration — context caching and OpenTelemetry.

Parsed from environment; consuming apps set these before calling
``agent_runtime.run_agent``. The test suite resets module state via
``_reset_adk_runtime_state()`` in ``agent_runtime``.
"""

from __future__ import annotations

import os

from google.adk.agents.context_cache_config import ContextCacheConfig
from google.genai import types

_context_cache_configured = False
_context_cache_config: ContextCacheConfig | None | object = object()

_otel_configured = False


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw else default


def get_context_cache_config() -> ContextCacheConfig | None:
    """Return ADK ``ContextCacheConfig`` when enabled, else ``None``.

    Enabled when ``DIALECTICA_CONTEXT_CACHE=true``. Tunables:
    ``DIALECTICA_CONTEXT_CACHE_INTERVALS`` (default 10),
    ``DIALECTICA_CONTEXT_CACHE_TTL_SECONDS`` (default 1800),
    ``DIALECTICA_CONTEXT_CACHE_MIN_TOKENS`` (default 4096 — Gemini hard floor),
    ``DIALECTICA_CONTEXT_CACHE_CREATE_TIMEOUT_MS`` (optional
    ``CachedContent.create()`` timeout).
    """
    global _context_cache_configured, _context_cache_config
    if _context_cache_configured:
        assert _context_cache_config is not object()
        return _context_cache_config  # type: ignore[return-value]

    _context_cache_configured = True
    if not _env_truthy("DIALECTICA_CONTEXT_CACHE"):
        _context_cache_config = None
        return None

    create_http_options: types.HttpOptions | None = None
    timeout_ms = os.environ.get("DIALECTICA_CONTEXT_CACHE_CREATE_TIMEOUT_MS", "")
    if timeout_ms:
        create_http_options = types.HttpOptions(timeout=int(timeout_ms))

    _context_cache_config = ContextCacheConfig(
        cache_intervals=_env_int("DIALECTICA_CONTEXT_CACHE_INTERVALS", 10),
        ttl_seconds=_env_int("DIALECTICA_CONTEXT_CACHE_TTL_SECONDS", 1800),
        min_tokens=_env_int("DIALECTICA_CONTEXT_CACHE_MIN_TOKENS", 4096),
        create_http_options=create_http_options,
    )
    return _context_cache_config


def telemetry_should_setup() -> bool:
    """Whether to invoke ADK's ``maybe_set_otel_providers`` on first LLM call."""
    if _env_truthy("DIALECTICA_ADK_TELEMETRY"):
        return True
    for key in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    ):
        if os.environ.get(key):
            return True
    return False


def ensure_otel_setup() -> None:
    """One-shot ADK OpenTelemetry provider setup (no-op when disabled)."""
    global _otel_configured
    if _otel_configured:
        return
    _otel_configured = True
    if not telemetry_should_setup():
        return
    from google.adk.telemetry.setup import maybe_set_otel_providers

    maybe_set_otel_providers()


def reset_adk_config_state() -> None:
    """Re-read env on next access (tests only)."""
    global _context_cache_configured, _context_cache_config, _otel_configured
    _context_cache_configured = False
    _context_cache_config = object()
    _otel_configured = False
