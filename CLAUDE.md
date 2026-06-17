# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dialectica is a reasoning-engine toolbox built on Google ADK. The genuine win is the **agentic** engine (`agentic.py`): a tool-using loop (act → observe → iterate) that lets a model do what a single forward pass cannot — measured 8/8 vs a single call's 0/8 for a small model on tasks requiring interaction. It also ships **execution-guided repair** (`repair.py`, verifier-in-the-loop: best-of-N reliability at ~1/3 the cost on verifiable tasks), a **dialectic** engine (thesis → antithesis → synthesis; auditable + criteria-steered, NOT better quality than a single call), and a legacy **Tree-of-Thoughts + GAN** baseline. Hard-won finding: no pure-LLM scaffold beats a prompt-matched single call on *self-contained* tasks — engines win only by adding capability (tools) or ground-truth verification. Published on PyPI as `dialectica`. Python 3.11+.

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

**Four engines, honest hierarchy** (controlled evals in `evals/results/`, README "Evaluation"):

- `agentic.py` — `AgenticEngine` / `create_agentic_engine`: **the genuine win**. A tool-using ADK loop; inject tools (read a file, run tests, query a service) and the agent acts → observes → iterates until the task is objectively done. The one engine that beats a single call, because it adds CAPABILITY a single forward pass lacks (not quality): small model **8/8 vs single-call 0/8** on the hidden-oracle benchmark (`evals/agentic_eval.py`). Tools are caller-injected, so it stays task-agnostic.
- `repair.py` — `create_repair_engine`: verifier-in-the-loop (`generate → verifier → repair-on-failure`). On verifiable tasks it *ties* matched-cost best-of-K on pass-rate but reaches it far cheaper (short-circuits: ~1/3 the calls). Verifier is an injected `Callable[[answer], (passed, feedback)]`; `solution_format` pins output shape. Returns `{final_answer, passed, attempts, history}`. Reproduce with `evals/repair_ablation.py`.
- `dialectic.py` — `create_dialectic_engine`: thesis → antithesis → synthesis spiral. Pure-LLM scaffold; a prompt-controlled eval showed it ties/loses a prompt-matched single call (**0-3-2** at every model size — it rearranges the model's own thinking, adding no information), so it's positioned for content-steering (`criteria`) + auditable reasoning, not raw quality. Beats plain ToT (8-2-0).
- `agent.py` — `create_engine` / `create_coordinator`: legacy Tree-of-Thoughts + GAN beam search; baseline only.

The pluggable-stage detail below describes the **legacy ToT engine** (`coordinator.py`); the repair and dialectic engines are simpler and self-contained.

Pluggable workflow — every stage is a `typing.Protocol` in `protocols.py`, swappable without touching the engine:

- `Generator.expand` → propose thoughts · `Evaluator.evaluate` → score & refine · `Selector.select` → choose frontier · `Synthesizer.synthesize` → final answer
- `coordinator.py` runs the 3 phases: Initialize → Explore (beam-search loop) → Synthesize. Sibling expansions/evaluations run concurrently via `asyncio.gather`.
- `agent.py` is the composition root (`create_engine`, `build_default_components`) — wiring only. Knobs: `score_threshold` (beam admission) vs `gan_score_threshold` (stop-refining bar), and `criteria` (discriminator rubric — steers answer content; default `DEFAULT_EVALUATION_CRITERIA`, feasibility-anchored).
- `agent_factory.py` builds ADK `LlmAgent`s from `ROLE_TEMPLATES` (Generator/Discriminator/Synthesizer). `agent_runtime.run_agent()` is the only place that actually calls the LLM; it retries transient failures with exponential backoff (`_call_agent_once` is the raw transport — retry tests patch that, everything else patches `run_agent`).
- Defaults: `LlmGenerator`, `AdversarialEvaluator` (GAN refine loop) / `SinglePassEvaluator`, `BeamSearch` / `GreedySearch`, `LlmSynthesizer`. Unparseable verdicts are re-asked up to 3 times (some backends, e.g. the qwen proxy, transiently return empty structured output ~7-10% of the time); 3 consecutive post-retry failures trip a circuit breaker that aborts the run.

All public stage methods are `async`. The library never calls `logging.basicConfig` — the consuming app owns logging setup.

Top-level `evals/` is the eval harness (dev tool, not shipped in the wheel): each benchmark problem (`problems.py`) is solved by the engine and by a single-call baseline (`baseline.py`), then a blind judge (`judge.py`) compares both answers twice with swapped positions — disagreement is a tie. `harness.py` counts LLM calls through the `run_agent` seam and renders the report. Model overrides: `BASELINE_MODEL_CONFIG` / `JUDGE_MODEL_CONFIG`.

Eval findings (2026-06, three 3-run × 5-problem matrices, see README "Results"): with the original "Innovation" discriminator criterion (V1) the engine won technical problems 7-1-1 but lost organizational ones 0-4-2 ("over-complex"), reproducing across Gemini and Qwen. Replacing "Innovation" with "Feasibility under stated constraints" (V2 + second seed V3) pooled to 20-8-2 (technical 15-2-1, organizational 5-6-1) vs V1's 7-5-3. Key insight: because the GAN loop refines thoughts against the critique, discriminator criteria steer answer content, not just selection. Engine cost ≈ 20-30× baseline calls; concurrency cut wall-clock 2-3× at unchanged call counts. Reports land in `evals/results/` (gitignored).

Prompt-controlled finding (2026-06-15, qwen3.6-35b-a3b via CLIPROXYAPI, blind position-swap) — **why repair is the core**: strengthening the dialectic (synthesis "dominate a single expert pass" + thesis baseline-strength) beat a *naively*-prompted single call (4-1-0) and plain ToT (pooled 8-2-0), but against a **prompt-matched** strong baseline it went **0-3-2 (loses) at equal length** — the gain was the prompt, not the structure. Lesson: pure-LLM scaffolds (ToT, GAN, dialectic) only rearrange the model's own thinking on one context, so they tie a single call; a scaffold beats one pass only by adding information a single pass lacks — tool-grounding (`repair.py`), scale, or independence. On verifiable tasks the band where repair beats a single call is *fails-but-fixable*, and it shrinks as the model strengthens (this model solved HumanEval 17-18/18 and curated LCB-hard at pass@1, leaving little gap to demonstrate).

SWE-suite findings (2026-06, ground truth): against a 1-attempt baseline the engine looked +1 (11/12 vs 10/12 on gpt-oss:20b; 10/12 vs 9/12 on gemma4:e4b), but rescue mode with a pass@2 screen dissolved it — the apparent lift was resampling luck, and the single real gap (max-fill on e4b) was NOT rescued (full mode even regressed min-path on e4b). After extending to 18 problems with the literature's hardest HumanEval items, cloud gemma-4 (31b-it and 26b-a4b-it via AI Studio) solved 18/18 at pass@2 — HumanEval-class is saturated for this family; real code-value evidence needs LiveCodeBench/competition difficulty. Methodology rules: compare scaffolds against pass@k at matched cost; the advice suite still needs a best-of-2-plus-judge control. Backend quirk: enforced JSON mode breaks gemma-4-26b-a4b-it (empty/truncated verdicts) — use `structured_output=False` / `--no-structured-output`.

## Gotchas

- The library does **not** load `.env` — consuming apps own that. Only the test suite loads it (`dialectica/.env`).
- Models: use `gemini-3.5-flash` (default) or `gemini-3.1-pro-preview` only — there is no stable `gemini-3.1-pro` (404 on generateContent). Configure via `provider:model_name` env vars (`DEFAULT_MODEL_CONFIG`, plus optional `GENERATOR_MODEL_CONFIG` / `DISCRIMINATOR_MODEL_CONFIG` / `SYNTHESIZER_MODEL_CONFIG`). Parsed in `llm_config.py`.
- Env vars: `GOOGLE_API_KEY` for AI Studio, or the Vertex trio (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`). See `.env.example` (repo root; copy to `dialectica/.env` for the test suite).

## Style

- 3.11+ type hints (`list[str]`, `str | None`), Pydantic v2 models, async throughout. Match surrounding code.

## Releasing

Conventional commits (use the `/git:commit` skill). Release = push a `v*.*.*` tag whose version **matches** `pyproject.toml`; CI (`.github/workflows/release.yml`) runs tests, then publishes to PyPI and creates a GitHub release.
