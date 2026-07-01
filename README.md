# Dialectica ![](https://img.shields.io/badge/A%20FRAD%20PRODUCT-WIP-yellow)

[![PyPI](https://img.shields.io/pypi/v/dialectica.svg)](https://pypi.org/project/dialectica/) [![Twitter Follow](https://img.shields.io/twitter/follow/FradSer?style=social)](https://twitter.com/FradSer) [![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![Framework](https://img.shields.io/badge/Framework-ADK%202.0+-orange.svg)]() [![Evaluation](https://img.shields.io/badge/Evaluation-honesty%20gate-purple.svg)]()

**English** | [简体中文](README.zh-CN.md)

**Dialectica** is a reasoning-engine toolbox on Google ADK, built and measured the hard way: every engine is run against a matched-cost baseline and a blind judge, and only the wins the data supports are kept. The rest are documented as negative results. The whole point is to answer one question — *does a scaffold beat a single well-prompted call?* — with numbers, not vibes.

> **The one-sentence finding.** On self-contained tasks, *no* pure-LLM scaffold (ToT, GAN, dialectic, heterogeneous ensemble) beats a prompt-matched single call on result quality — they only rearrange the model's own thinking, adding no information. An engine wins only by doing what one forward pass cannot: **acting on the world** (agentic), **running ground-truth verification** (repair), or — measured, partial — **sampling independent models** (ensemble robustness, but the signal is heterogeneity, not the scorer). See [Evaluation](#evaluation).

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch), Sakana AI's AB-MCTS / collective-intelligence line, and Claude Code's composable workflows.

## The engine hierarchy (data-justified)

Pick by what your task lacks in a single call:

| Engine | Wins by adding | Verdict |
|---|---|---|
| **Agentic** (`create_agentic_engine`) | **capability** — tools let the model act → observe → iterate | ✅ genuine win (8/8 vs 0/8 on hidden-oracle) |
| **Repair** (`create_repair_engine`) | **ground truth** — verifier-in-the-loop, short-circuits on pass | ✅ cost win (best-of-N reliability at ~1/3 the calls) |
| **Ensemble** (`create_ensemble_engine`) | **independence** — heterogeneous roster | ⚠️ on probation / CUT (robustness gain is heterogeneity, not the scorer) |
| **Dialectic** (`create_dialectic_engine`) | — pure-LLM scaffold | ❌ ties a single call (0-3-2); auditable trace only |
| **ToT + GAN** (`create_engine`) | — pure-LLM scaffold | ❌ dominated (0-4-1 / 0-2-3 / 0-1-4); baseline only |

## Install

```bash
uv add dialectica      # or: pip install dialectica
```

```python
import os, asyncio
from dialectica import create_repair_engine

os.environ["GOOGLE_API_KEY"] = "..."          # the app owns env setup

# A verifier returns (passed, feedback) for ANY objective check — unit tests,
# a JSON schema, a linter, assertion-checked logic. The engine repairs against
# the feedback until it passes or runs out of attempts.
def verify(answer: str) -> tuple[bool, str]:
    ok = "def solve" in answer                 # your real check goes here
    return ok, "" if ok else "no solve() function defined"

async def main():
    result = await create_repair_engine(
        "Write a solve() function that ...", verifier=verify
    ).run()
    print(result["passed"], result["attempts"], result["final_answer"])

asyncio.run(main())
```

Prefer `create_repair_engine` for verifiable tasks (it's the core). For
multi-step tool-using tasks use `create_agentic_engine`. The library reads
configuration from `os.environ` and does **not** load `.env` itself.

## Engines & primitives

### 🤖 Agentic engine — adds capability (`create_agentic_engine`)
The one engine that lets a model do what a single forward pass *cannot*: a
tool-using loop. Inject your tools (read a file, run tests, query a service);
the agent plans, calls a tool, reads the result, and iterates until the task is
objectively done — ADK drives the loop.

- **Wins by capability, not quality** — measured **8/8 vs a single call's 0/8** for a small model on tasks that require gathering information through tools (`evals/agentic_eval.py`). This is the genuine value class; reasoning scaffolds on self-contained prompts tie a single call.
- **Task-agnostic** — tools are injected callables; ADK derives their schemas.
- **Returns** `{final_answer}`; side effects happen through your tools, so you check the objective outcome afterward.

### 🛠️ Execution-guided repair — verifier-in-the-loop (`create_repair_engine`)
For verifiable tasks: **generate → run an injected verifier → repair against the
concrete failure → retry**, until it passes or attempts run out.

- **Task-agnostic verifier** — any `Callable[[answer], (passed, feedback)]`: unit tests, a schema validator, a linter, assertion-checked logic. `solution_format` pins the output shape your verifier parses.
- **Uses the full failure history** — every prior attempt + its exact failure is fed back, so the loop doesn't oscillate between two wrong fixes.
- **Cost-disciplined** — short-circuits the moment the verifier passes, reaching best-of-N reliability at a fraction of the calls.
- **Multi-model** — pass `models=[...]` to rotate across a roster on failure; the per-attempt `history[i]["model"]` records which model produced each attempt.
- **Returns** `{final_answer, passed, attempts, history}`.

Measure it against pass@1 and matched-cost best-of-K with `uv run python -m evals.repair_ablation`.

### 🌐 Ensemble search engine (`create_ensemble_engine`) — *on probation*
AB-MCTS-lite adaptive search over a heterogeneous model roster (wider = sample a
fresh model, deeper = refine the best), ranked by a **mandatory injected float
scorer**. Designed as a fourth honest win lever — *independence* (different
training distributions) ranked by a ground-truth-grade signal.

**The honesty gate cut it** (Evaluation finding #5): on open-ended meta tasks the
ensemble *did* beat a single call under a blind judge (**3-1-2**), but a
**blind-pick** arm (signal replaced by a constant) matched it (**3-1**) — the
gain is **roster heterogeneity, not the scorer's signal**. On verifiable code
both arms saturated (6/6). Kept for study; a no-scorer multi-model best-of-N
captures the measured robustness gain more honestly.

- **Mandatory scorer** (`Callable[[str], float]` or async) — constructing without one raises; pure-scaffold misuse is unrepresentable. Wrap a boolean verifier with `lambda a: 1.0 if v(a)[0] else 0.0`.
- **Injectable policy** — default Thompson-sampling bandit; tests inject a scripted deterministic policy.
- **FR6 roster-distinctness** — warns when two members resolve to the same effective model or silently fall back to the default.
- **Returns** `{final_answer, passed, attempts, history, best_score}`.

### 🔗 Workflow primitives — composable multi-agent runtime (`Workflow`)
A Python re-implementation of Claude Code's `Workflow` orchestration surface:
`agent()` / `parallel()` / `pipeline()` / `phase()` / `log()` / `budget()`. For
*meta-task* orchestration (research, review, planning, design) — the regime
where generate → adversarial-judge → synthesize genuinely helps. It is an
**orchestration layer**, not a self-contained-quality engine: the negative
findings above stand, and composing a workflow over these primitives does not
repeal them.

### 🧩 Dialectic engine (`create_dialectic_engine`)
*Thesis → antithesis → synthesis*: a self-contained spiral that produces an
**auditable** reasoning trace, steered by `criteria`. A pure-LLM scaffold —
useful for transparency and content-steering, but (measured) **not** a
result-quality win over a single call. Its value is the auditable trace and
criteria-steering, not better answers.

### 🌳 Tree-of-Thoughts + GAN engine (`create_engine`)
The prior-generation pluggable pipeline (beam search + GAN-style adversarial
refinement, every stage a swappable `Protocol`). **Measured dominated** at
matched compute (loses to single, best-of-N, and flat self-refine); kept for
study and back-compat, not recommended for quality.

## Evaluation

Does the engine actually beat a single strong-model call? The repo ships an
eval harness (`evals/`, a dev tool — not part of the published package) that
answers this with data: each problem is solved by the engine **and** by a
single-call baseline; a **blind judge** compares both answers twice with
positions swapped (disagreement = tie); LLM calls are counted through the same
`run_agent` seam the tests mock.

```bash
uv run python -m evals                          # all benchmark problems
uv run python -m evals.repair_ablation          # repair vs best-of-K
uv run python -m evals.agentic_eval             # agentic vs single (hidden oracle)
uv run python -m evals.quality_ablation         # ToT+GAN vs single/best-of-N/self-refine
uv run python -m evals.ensemble_ablation        # ensemble 3-arm honesty gate (code)
uv run python -m evals.ensemble_meta_ablation   # ensemble honesty gate (open-ended, LLM judge)
```

### Headline findings (measured, no preset conclusion)

1. **Where an engine genuinely wins — capability, not quality.** On tasks that require *acting* (the agentic hidden-oracle benchmark), a small model with the **agentic engine** scored **8/8** vs a single call's **0/8**: it probes the hidden function, infers the rule, and implements it — a single call can't know an arbitrary rule without probing. This is the genuine value class. Reproduce: `uv run python -m evals.agentic_eval`.

2. **Where scaffolds do NOT win — self-contained result quality.** Judged against a *matched-cost* baseline, **no pure-LLM scaffold beats a single call**: the dialectic went **0-3-2** vs a prompt-matched strong baseline at every model size (the earlier 4-1-0 "win" was prompt + length, not structure). The **repair** engine beats a *single* call but exactly **ties matched-cost best-of-K** on pass-rate — its real edge is **cost** (best-of-N reliability at ~1/3 the calls). Reproduce: `uv run python -m evals.repair_ablation`.

3. **The tree structure is *dominated*, not just unhelpful.** On **Game-of-24** — ToT's *own* canonical benchmark — a faithful ToT scored **14/15 and lost to a single call's 15/15 at ~34× the cost**: modern models one-shot the task the 2023 paper's GPT-4 failed 96% of the time. At matched compute under a blind judge, the ToT+GAN engine went **0-4-1 / 0-2-3 / 0-1-4** (vs single / best-of-N / self-refine) — it *never won a matchup*. The quality order is **self-refine ≥ best-of-N ≥ single ≥ tree-scaffold**. Reproduce: `uv run python -m evals.game24` and `uv run python -m evals.quality_ablation`.

4. **The value window is closed across the accessible model range.** ToT only helps where the base model fails alone but search can recover — a "fails-but-fixable" band. Probing the *hardest* Game-of-24 puzzles against **four model tiers** (the weakest cloud models available) a single call scored **5/5 on every model, every puzzle**. There is no accessible weak model that fails these tasks, so there is no gap for search to recover — the boundary has moved past this task.

5. **Heterogeneous ensemble — the scorer's signal is not what does the work (2026-06-26).** The ensemble was designed as a fourth honest win lever — *independence* ranked by a mandatory ground-truth-grade signal. A two-axis honesty gate falsified the signal half of the thesis while surfacing a real, narrower result:
   - **Code (ground-truth verifier, 6 problems, budget 6):** ensemble+signal **6/6**, best-single best-of-6 **6/6**, blind-pick **6/6** — **CUT**: both models one-shot every problem, so heterogeneity and the signal both have empty headroom. Saturation, same shape as finding #4.
   - **Open-ended meta (blind LLM-judge, 5 problems, budget 6, position-swap):** ensemble+signal beat a prompt-matched single call **3-1-2** — *the engine does improve answer robustness on open-ended tasks* (the code axis couldn't measure this). But the **blind-pick arm** (signal replaced by a constant) also beat single **3-1**: the gain is **attributable to roster heterogeneity, not the scorer's ranking signal**. Per H1's signal-attribution clause: **CUT**.
   - **Takeaway:** a *no-scorer* multi-model best-of-N (sample N heterogeneous models, keep one) captures the robustness gain the ensemble shows on open-ended tasks; the float scorer adds no measurable lift over blind-pick. The repair sub-criterion was also **CUT** (multi-model-repair@6 vs single@6: 6/6 vs 6/6, **0 model-switch rescues**). Reproduce: `uv run python -m evals.ensemble_ablation` and `uv run python -m evals.ensemble_meta_ablation` (need a live multi-provider roster via `OPENAI_API_BASE`/`OPENAI_API_KEY`, e.g. a cliproxy exposing qwen + glm; `DIALECTICA_DISABLE_THINKING=true` for qwen-family latency).

### The law these findings all point to

A scaffold beats one forward pass **iff** it adds information a single pass
lacks — **tools** (agentic), **ground-truth verification** (repair), or
**independent samples** (ensemble robustness, but only via heterogeneity, not a
learned ranking). Pure rearrangement of one model's thinking on one context
(ToT, GAN, dialectic, an LLM-judge scorer over same-family candidates) ties a
single call. Sakana AI's portfolio converges on the same law from the other
side: every genuine win there is also backed by a ground-truth oracle external
to the model.

### Earlier advice-suite matrices (2026-06-10/11) — superseded

The first-round matrices compared the ToT+GAN engine against a *weaker*
single-call baseline (no matched-prompt control) and an "Innovation"
discriminator criterion that steered toward over-complex answers. They are
superseded by findings #2–#5 above. Kept in `evals/results/` for reproducibility:
V1 (Innovation criterion) won technical problems 7-1-1 but lost organizational
ones 0-4-2; V2 (Feasibility criterion) pooled to 20-8-2 vs V1's 7-5-3 —
evidence that discriminator criteria steer answer *content*, not just selection,
but neither beats a prompt-matched strong baseline.

## Configuration

All config is read from `os.environ` — as a library, Dialectica does **not**
load `.env` itself; the consuming app owns environment setup. Only the test
suite loads `dialectica/.env`.

```bash
# Default model for all agents
export DEFAULT_MODEL_CONFIG="google:gemini-3.5-flash"

# Role-specific overrides (optional)
export GENERATOR_MODEL_CONFIG="google:gemini-3.5-flash"
export DISCRIMINATOR_MODEL_CONFIG="google:gemini-3.1-pro-preview"
export SYNTESIZER_MODEL_CONFIG="google:gemini-3.5-flash"
export JUDGE_MODEL_CONFIG="google:gemini-3.1-pro-preview"

# Google AI Studio
export GOOGLE_API_KEY="..."

# Or Vertex AI
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="..."
export GOOGLE_CLOUD_LOCATION="..."

# OpenRouter
export OPENROUTER_API_KEY="..."

# OpenAI-compatible (proxy / vLLM / cliproxy)
export OPENAI_API_KEY="..."
export OPENAI_API_BASE="http://localhost:8317/v1"
# Disable qwen-family thinking trace for eval latency (optional)
export DIALECTICA_DISABLE_THINKING=true
```

Use `gemini-3.5-flash` (default) or `gemini-3.1-pro-preview` only — there is no
stable `gemini-3.1-pro` (404 on generateContent). Provider strings are
`provider:model_name`; the `openai:` provider passes `api_base` explicitly
(recent LiteLLM no longer reads `OPENAI_API_BASE` for the `openai/` prefix).

### Engine parameters

- **Agentic** — `tools` (injected callables), `instructions` (task-specific guidance).
- **Repair** — `verifier` (mandatory), `max_attempts`, `solution_format`, `models` (optional roster).
- **Ensemble** — `scorer` (mandatory), `models` (roster), `max_calls`, `solved_score`, `policy` (default Thompson bandit).
- **Dialectic** — `criteria` (steers synthesis content), `rounds`.
- **Workflow** — `budget_total`, `concurrency` (or `DIALECTICA_WORKFLOW_CONCURRENCY`).

## Usage examples

### Repair (verifiable task)

```python
from dialectica import create_repair_engine

def verify(code: str) -> tuple[bool, str]:
    # your real check — run the tests, validate the schema, etc.
    return True, ""

engine = create_repair_engine("Write solve()", verifier=verify, max_attempts=3)
result = await engine.run()
# {"final_answer", "passed", "attempts", "history"}
```

### Agentic (tool-using task)

```python
from dialectica import create_agentic_engine

engine = create_agentic_engine("Fix the failing test", tools=[read_file, run_tests])
result = await engine.run()   # tools do the acting; check the outcome after
```

### Ensemble (heterogeneous roster)

```python
from dialectica import create_ensemble_engine

def scorer(answer: str) -> float: ...      # your ground-truth-grade rank

engine = create_ensemble_engine(
    "Design the pricing tier",
    scorer=scorer,
    models=["google:gemini-3.5-flash", "openrouter:qwen3.6-32b"],
    max_calls=8,
)
result = await engine.run()
# {"final_answer", "passed", "attempts", "history", "best_score"}
```

### Inspecting the result

All engines return a `dict` with `final_answer`, `passed` (or implicit), `attempts`,
and `history`. The ensemble and repair `history` entries carry the producing
model per attempt, so you can attribute wins to a specific arm or to
model-switching.

## The ToT + GAN engine (legacy, deep-dive)

The pluggable pipeline every stage is a `typing.Protocol` in `protocols.py`:
`Generator.expand` → `Evaluator.evaluate` → `Selector.select` →
`Synthesizer.synthesize`. `coordinator.py` runs three phases (Initialize →
Explore → Synthesize) with sibling expansions/evaluations concurrent via
`asyncio.gather`. Knobs: `score_threshold` (beam admission) vs
`gan_score_threshold` (stop-refining bar), and `criteria` (the discriminator
rubric — steers answer content, not just selection).

Defaults: `LlmGenerator`, `AdversarialEvaluator` (GAN refine loop) /
`SinglePassEvaluator`, `BeamSearch` / `GreedySearch`, `LlmSynthesizer`.
Unparseable verdicts are re-asked up to 3 times; 3 consecutive post-retry
failures trip a circuit breaker that aborts the run. All public stage methods
are `async`.

This engine is **measured dominated** (finding #3) — keep it for study and
back-compat, not for quality.

## Development

```bash
uv sync                                         # install deps
uv run pytest                                   # mocked, fast, no API key
uv run pytest -m e2e                            # live E2E (needs GOOGLE_API_KEY)
uv run ruff format && uv run ruff check         # format / lint
```

The library never calls `logging.basicConfig` — the consuming app owns logging.
Mock the LLM at the single seam `agent_runtime.run_agent()` — never patch ADK
internals or per-stage agents (`tests/helpers.py` has the fakes). `asyncio_mode =
auto`; pytest-bdd steps are sync, so wrap coroutines with `asyncio.run()`.

## Testing workflow (BDD-driven TDD)

New behavior starts with a Gherkin scenario in `tests/features/*.feature`,
executable via pytest-bdd — step definitions live in `tests/test_*_feature.py`
(bound with `scenarios(...`). Then RED test → GREEN code → REFACTOR. When
updating tests, update the matching `.feature` first. CI
(`.github/workflows/test.yml`) runs `ruff format --check`, `ruff check`, and
`pytest` on every push/PR.

## Project structure

```
dialectica/
  agent.py            # legacy ToT+GAN composition root (create_engine)
  agent_factory.py    # builds LlmAgents from ROLE_TEMPLATES
  agent_runtime.py    # THE single LLM seam: run_agent() + retry/backoff
  agentic.py          # create_agentic_engine (the genuine win)
  coordinator.py      # legacy ToT Explore/Synthesize loop
  dialectic.py        # create_dialectic_engine (auditable trace, no quality win)
  ensemble.py         # create_ensemble_engine (on probation / CUT)
  gan_evaluator.py    # AdversarialEvaluator + verdict parsing/repair
  llm_config.py       # provider:model parsing (google/openrouter/openai)
  models.py           # ThoughtData / EvaluationResult / DiscriminatorVerdict
  protocols.py        # Generator/Evaluator/Selector/Synthesizer Protocols
  repair.py           # create_repair_engine (cost win)
  workflow.py         # Workflow + agent/parallel/pipeline/phase/log/budget
evals/                # dev-only eval harness (not shipped in the wheel)
tests/                # BDD features + step defs + helpers
docs/plans/           # design + plan folders (brainstorming/writing-plans)
```

## Troubleshooting

- **`gemini-3.1-pro` 404s** — use `gemini-3.1-pro-preview` or `gemini-3.5-flash`.
- **OpenAI-compatible backend "Connection error"** — `OPENAI_API_BASE` is no longer read for the `openai/` prefix by recent LiteLLM; the library passes `api_base` explicitly, so make sure `OPENAI_API_BASE` is set (not just `OPENAI_API_KEY`).
- **qwen-family evals are slow** — set `DIALECTICA_DISABLE_THINKING=true` to disable the reasoning trace (`chat_template_kwargs.enable_thinking=false`).
- **Ensemble roster "collapsed to duplicate effective model"** — two members resolved to the same model (often a provider key is unset, so both silently fell back to the default). Set the provider's API key or use distinct models.
- **Enforced JSON mode returns empty verdicts** (some backends, e.g. gemma-4-26b-a4b) — use `structured_output=False` / `--no-structured-output`.

## Contributing

Conventional commits (use the `/git:commit` skill). Release = push a `v*.*.*`
tag whose version **matches** `pyproject.toml`; CI runs tests, publishes to PyPI,
and creates a GitHub release. When adding an engine, ship the honesty-gate
ablation that would CUT it if the data says so — the repo's tradition is
documented negative results, not unproven claims.

## License

MIT — see `LICENSE`.

## References

- [Tree of Thoughts](https://arxiv.org/abs/2305.10601) — Yao et al., 2023 (the ToT engine's lineage; now a baseline).
- [Sakana AB-MCTS / "Wider or Deeper?"](https://arxiv.org/abs/2503.04412) — the ensemble engine's lineage (independence + ground-truth signal).
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — inspiration.

## Acknowledgments

Built on Google ADK. The honesty-gate methodology owes to the blind
position-swapped judge pattern used across LLM evals.
