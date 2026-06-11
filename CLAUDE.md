# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dialectica is a pluggable adversarial reasoning engine: Tree-of-Thoughts search with GAN-style adversarial evaluation (thesis → antithesis → synthesis), built on Google ADK. Published on PyPI as `dialectica`. Python 3.11+.

## Commands

- Install deps: `uv sync`
- Test (mocked, fast, no API key): `uv run pytest`
- Test live E2E (calls real Gemini, needs `GOOGLE_API_KEY`): `uv run pytest -m e2e` — auto-skipped without the key
- Eval (engine vs single-call baseline, real API): `uv run python -m evals [--limit N --json out.json]`
- Format / lint: `uv run ruff format` / `uv run ruff check`
- Never hand-edit `pyproject.toml`; use `uv add` / `uv remove`.

## Testing workflow

BDD-driven TDD: new behavior starts with a Gherkin scenario in `tests/features/*.feature`, executable via pytest-bdd — step definitions live in `tests/test_*_feature.py` (bound with `scenarios(...)`). Then RED test → GREEN code → REFACTOR. When updating tests, update the matching `.feature` first.

Mock the LLM at the single seam `agent_runtime.run_agent()` — never patch ADK internals or per-stage agents (`tests/helpers.py` has the fakes). `asyncio_mode = auto`, so plain async tests need no decorator; pytest-bdd steps are sync — wrap coroutines with `asyncio.run()`. Tests load `dialectica/.env` via `tests/conftest.py`.

CI (`.github/workflows/test.yml`) runs `ruff format --check`, `ruff check`, and `pytest` on every push/PR; the release workflow runs the same gates.

## Architecture

Pluggable workflow — every stage is a `typing.Protocol` in `protocols.py`, swappable without touching the engine:

- `Generator.expand` → propose thoughts · `Evaluator.evaluate` → score & refine · `Selector.select` → choose frontier · `Synthesizer.synthesize` → final answer
- `coordinator.py` runs the 3 phases: Initialize → Explore (beam-search loop) → Synthesize. Sibling expansions/evaluations run concurrently via `asyncio.gather`.
- `agent.py` is the composition root (`create_engine`, `build_default_components`) — wiring only. Knobs: `score_threshold` (beam admission) vs `gan_score_threshold` (stop-refining bar), and `criteria` (discriminator rubric — steers answer content; default `DEFAULT_EVALUATION_CRITERIA`, feasibility-anchored).
- `agent_factory.py` builds ADK `LlmAgent`s from `ROLE_TEMPLATES` (Generator/Discriminator/Synthesizer). `agent_runtime.run_agent()` is the only place that actually calls the LLM; it retries transient failures with exponential backoff (`_call_agent_once` is the raw transport — retry tests patch that, everything else patches `run_agent`).
- Defaults: `LlmGenerator`, `AdversarialEvaluator` (GAN refine loop) / `SinglePassEvaluator`, `BeamSearch` / `GreedySearch`, `LlmSynthesizer`. Unparseable verdicts are re-asked up to 3 times (some backends, e.g. the qwen proxy, transiently return empty structured output ~7-10% of the time); 3 consecutive post-retry failures trip a circuit breaker that aborts the run.

All public stage methods are `async`. The library never calls `logging.basicConfig` — the consuming app owns logging setup.

Top-level `evals/` is the eval harness (dev tool, not shipped in the wheel): each benchmark problem (`problems.py`) is solved by the engine and by a single-call baseline (`baseline.py`), then a blind judge (`judge.py`) compares both answers twice with swapped positions — disagreement is a tie. `harness.py` counts LLM calls through the `run_agent` seam and renders the report. Model overrides: `BASELINE_MODEL_CONFIG` / `JUDGE_MODEL_CONFIG`.

Eval findings (2026-06, three 3-run × 5-problem matrices, see README "Results"): with the original "Innovation" discriminator criterion (V1) the engine won technical problems 7-1-1 but lost organizational ones 0-4-2 ("over-complex"), reproducing across Gemini and Qwen. Replacing "Innovation" with "Feasibility under stated constraints" (V2 + second seed V3) pooled to 20-8-2 (technical 15-2-1, organizational 5-6-1) vs V1's 7-5-3. Key insight: because the GAN loop refines thoughts against the critique, discriminator criteria steer answer content, not just selection. Engine cost ≈ 20-30× baseline calls; concurrency cut wall-clock 2-3× at unchanged call counts. Reports land in `evals/results/` (gitignored).

## Gotchas

- The library does **not** load `.env` — consuming apps own that. Only the test suite loads it (`dialectica/.env`).
- Models: use `gemini-3.5-flash` (default) or `gemini-3.1-pro-preview` only — there is no stable `gemini-3.1-pro` (404 on generateContent). Configure via `provider:model_name` env vars (`DEFAULT_MODEL_CONFIG`, plus optional `GENERATOR_MODEL_CONFIG` / `DISCRIMINATOR_MODEL_CONFIG` / `SYNTHESIZER_MODEL_CONFIG`). Parsed in `llm_config.py`.
- Env vars: `GOOGLE_API_KEY` for AI Studio, or the Vertex trio (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`). See `.env.example` (repo root; copy to `dialectica/.env` for the test suite).

## Style

- 3.11+ type hints (`list[str]`, `str | None`), Pydantic v2 models, async throughout. Match surrounding code.

## Releasing

Conventional commits (use the `/git:commit` skill). Release = push a `v*.*.*` tag whose version **matches** `pyproject.toml`; CI (`.github/workflows/release.yml`) runs tests, then publishes to PyPI and creates a GitHub release.
