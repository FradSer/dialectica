# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dialectica is a pluggable adversarial reasoning engine: Tree-of-Thoughts search with GAN-style adversarial evaluation (thesis → antithesis → synthesis), built on Google ADK. Published on PyPI as `dialectica`. Python 3.11+.

## Commands

- Install deps: `uv sync`
- Test (mocked, fast, no API key): `uv run pytest`
- Test live E2E (calls real Gemini, needs `GOOGLE_API_KEY`): `uv run pytest -m e2e` — auto-skipped without the key
- Format / lint: `uv run ruff format` / `uv run ruff check`
- Never hand-edit `pyproject.toml`; use `uv add` / `uv remove`.

## Testing workflow

BDD-driven TDD: new behavior starts with a Gherkin scenario in `tests/features/*.feature`, executable via pytest-bdd — step definitions live in `tests/test_*_feature.py` (bound with `scenarios(...)`). Then RED test → GREEN code → REFACTOR. When updating tests, update the matching `.feature` first.

Mock the LLM at the single seam `agent_runtime.run_agent()` — never patch ADK internals or per-stage agents (`tests/helpers.py` has the fakes). `asyncio_mode = auto`, so plain async tests need no decorator; pytest-bdd steps are sync — wrap coroutines with `asyncio.run()`. Tests load `dialectica/.env` via `tests/conftest.py`.

CI (`.github/workflows/test.yml`) runs `ruff format --check`, `ruff check`, and `pytest` on every push/PR; the release workflow runs the same gates.

## Architecture

Pluggable workflow — every stage is a `typing.Protocol` in `protocols.py`, swappable without touching the engine:

- `Generator.expand` → propose thoughts · `Evaluator.evaluate` → score & refine · `Selector.select` → choose frontier · `Synthesizer.synthesize` → final answer
- `coordinator.py` runs the 3 phases: Initialize → Explore (beam-search loop) → Synthesize.
- `agent.py` is the composition root (`create_engine`, `build_default_components`) — wiring only.
- `agent_factory.py` builds ADK `LlmAgent`s from `ROLE_TEMPLATES` (role → system prompt). `agent_runtime.run_agent()` is the only place that actually calls the LLM.
- Defaults: `LlmGenerator`, `AdversarialEvaluator` (GAN refine loop) / `SinglePassEvaluator`, `BeamSearch` / `GreedySearch`, `LlmSynthesizer`.

All public stage methods are `async`.

## Gotchas

- The library does **not** load `.env` — consuming apps own that. Only the test suite loads it (`dialectica/.env`).
- Models: use `gemini-3.5-flash` (default) or `gemini-3.1-pro` only. Configure via `provider:model_name` env vars (`DEFAULT_MODEL_CONFIG`, plus optional `GENERATOR_MODEL_CONFIG` / `DISCRIMINATOR_MODEL_CONFIG` / `SYNTHESIZER_MODEL_CONFIG`). Parsed in `llm_config.py`.
- Env vars: `GOOGLE_API_KEY` for AI Studio, or the Vertex trio (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`). See `dialectica/.env.example`.

## Style

- 3.11+ type hints (`list[str]`, `str | None`), Pydantic v2 models, async throughout. Match surrounding code.

## Releasing

Conventional commits (use the `/git:commit` skill). Release = push a `v*.*.*` tag whose version **matches** `pyproject.toml`; CI (`.github/workflows/release.yml`) runs tests, then publishes to PyPI and creates a GitHub release.
