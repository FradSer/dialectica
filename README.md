# Dialectica ![](https://img.shields.io/badge/A%20FRAD%20PRODUCT-WIP-yellow)

[![PyPI](https://img.shields.io/pypi/v/dialectica.svg)](https://pypi.org/project/dialectica/) [![Twitter Follow](https://img.shields.io/twitter/follow/FradSer?style=social)](https://twitter.com/FradSer) [![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![Framework](https://img.shields.io/badge/Framework-ADK%202.11+-orange.svg)](https://github.com/google/adk-python) [![Evaluation](https://img.shields.io/badge/Evaluation-honesty%20gate-purple.svg)](#evaluation)

**English** | [简体中文](README.zh-CN.md)

**Dialectica** is an auditable reasoning-workflow and evaluation toolbox on Google ADK. It combines a composable execution kernel with verifier-guided repair, and tests research patterns against strong single-call and repeated-call controls. Its question is: *when does additional orchestration improve reliability, quality or cost?* Real calls, failed attempts, missing usage and inconclusive judgments are part of the evidence.

> **Historical findings.** Tested ToT/GAN/scorer scaffolds did not improve quality over the tested strong single-call controls on self-contained tasks. Tool access and objective repair provided capability or cost benefits. Open-ended experiments found gains for heterogeneous reflection (**10-0-0** on a ten-task pool) and a tuned dialectic (three tasks, one judge; see finding #9). These observations have limited evaluation coverage and do not establish a universal rule about inference-time computation. New research modes must pass independent comparisons before promotion. See [Evaluation](#evaluation).

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch), Sakana AI's AB-MCTS / collective-intelligence line, and Claude Code's composable workflows.

## The public API (data-justified)

The evals collapsed the shipped surface to exactly what the data supports:

| | Wins by adding | Evidence (tested tasks/models) |
|---|---|---|
| **`Workflow` / `agent(tools=...)`** | **capability** — tools let a stage act → observe → iterate | ✅ capability gain on the hidden-oracle task (8/8 vs 0/8) |
| **`create_repair_engine`** | **ground truth** — verifier-in-the-loop, short-circuits on pass | ✅ lower cost at the tested pass rate (best-of-N reliability at ~1/3 the calls) |

Everything else this project built — a dedicated agentic-engine class, the heterogeneous ensemble + scorer, the dialectic spiral, the legacy ToT+GAN beam search — either needs nothing beyond `agent(tools=...)` or was measured to tie/lose a prompt-matched single call as a pure-LLM scaffold. They're kept as runnable **reference patterns**, not shipped API. For open-ended meta-tasks the measured recipe is hetero reflection (`examples/patterns/reflection_pattern.py`) composed on the kernel — still not a third shipped engine. See [Patterns](#patterns-not-shipped-for-reference).

## Install

```bash
uv add dialectica      # or: pip install dialectica
```

```python
import os, asyncio
from dialectica import create_repair_engine

os.environ["GOOGLE_API_KEY"] = "..."  # the app owns env setup


# A verifier returns (passed, feedback) for ANY objective check — unit tests,
# a JSON schema, a linter, assertion-checked logic. The engine repairs against
# the feedback until it passes or runs out of attempts.
def verify(answer: str) -> tuple[bool, str]:
    ok = "def solve" in answer  # your real check goes here
    return ok, "" if ok else "no solve() function defined"


async def main():
    result = await create_repair_engine(
        "Write a solve() function that ...", verifier=verify
    ).run()
    print(result["passed"], result["attempts"], result["final_answer"])


asyncio.run(main())
```

Prefer `create_repair_engine` for verifiable tasks. For multi-step tool-using
tasks, build a `Workflow` script and call `agent(task, tools=[...])` directly
(see below). The library reads configuration from `os.environ` and does
**not** load `.env` itself.

## Workflow kernel & repair

### 🔗 `Workflow` / `agent` / `parallel` / `pipeline` — the execution kernel
A composable multi-agent runtime — the programmatic surface Claude Code's
`Workflow` tool provides (IDE host UI excluded): `agent()` / `parallel()` /
`pipeline()` / `workflow()` / `phase()` / `log()` / `budget()` / `run_id()`.
For *meta-task* orchestration (research, review, planning, design).

- **`agent(prompt, *, schema=None, tools=None, instructions="", label=None, phase=None, model=None, isolation=None, agent_type=None, sees=None)`** — one workflow agent step, potentially containing multiple model turns. `schema` requests structured JSON; **`tools`** is the capability-add lever (8/8 vs 0/8 on hidden-oracle). `isolation="worktree"` runs in a fresh git worktree (auto-removed if clean). `agent_type` (e.g. `"Explore"`) applies a read-only exploration charter. ADK supports `tools` + `schema` through model capabilities and a response-tool fallback. **`sees`** is a per-step access list (inspired by Sakana Fugu-Ultra's anti-"orchestration-collapse" mechanism): default is full isolation (an agent never sees another agent's transcript); `sees=["gather","critique"]` injects only the named prior steps' outputs into this call's prompt. Unknown/unfinished labels are skipped, not errors, so access lists survive conditional branches.
- **`workflow(script_or_name, *, args=None)`** — inline child workflow (one nesting level); shares outer budget. Pass a registered name via `register_workflow`.
- **`parallel(thunks)`** / **`pipeline(items, *stages)`** — concurrent barrier / per-item staged flow; max 4,096 items per call; 1,000 `agent()` calls per run.
- **Resume** — each run journals `agent()` calls under `.dialectica/workflows/<run_id>/`; `Workflow(..., resume_run_id=...)` replays the longest unchanged prefix from cache.
- **`Workflow(..., meta={...})`** — optional `name`/`description`/`phases` metadata; phase titles must match `phase()` calls.
- **Honest scope**: schema-only judge/synthesize workflows (no `tools`) remain pure-LLM scaffolds; evaluate their benefit under the task, model and cost conditions rather than assuming one.

```python
from dialectica import Workflow
from dialectica import workflow as wf
from dialectica.workflow import register_workflow


async def research(args):
    wf.phase("Gather")
    return await wf.agent(f"Research: {args['topic']}")


register_workflow("research", research)


async def main():
    return await Workflow(
        research,
        args={"topic": "cache design"},
        meta={
            "name": "research",
            "description": "fan-out research",
            "phases": [{"title": "Gather"}],
        },
    ).run()
```

### Claude Workflow parity — and what small models can gain from it

Dialectica's `Workflow` kernel is a **programmatic port** of Claude Code's
`Workflow` tool surface (IDE host UI excluded). You can express the same
orchestration patterns — fan-out, staged pipelines, child workflows, resume,
worktree isolation — as plain Python instead of a host-managed workflow file.

| Claude Code Workflow | Dialectica |
|---|---|
| `agent` / `parallel` / `pipeline` / `phase` / `log` / `budget` | ✅ |
| Child workflow, `run_id`, resume/journal | ✅ |
| `agent(isolation="worktree")` | ✅ |
| `agent_type` (e.g. read-only Explore) | ✅ Explore preset only |
| Named workflow registry | ✅ `register_workflow` |
| IDE `/workflows` UI, full agent-type roster (Plan, …) | ❌ API-only |
| Deep host integration (terminal, file tree) | Bring your own `tools` |

**Can this make a small model perform better?** Historical gains involved tools,
objective feedback, heterogeneous models or a tuned dialectic. These findings
have model/task/budget conditions; they do not establish a necessary condition
for improvement. Compare the workflow with a strong single-call baseline for
each model, and report actual costs before claiming a gain.

| Situation | What to use | Small-model upside |
|---|---|---|
| Must read code, run commands, probe an API | `agent(tools=[...])`, optional `parallel` | ✅ **Capability gain** — hidden-oracle **8/8 vs 0/8** for a small model with tools vs 0/8 single-call |
| Output is checkable (tests, schema, linter) | `create_repair_engine` + verifier | ✅ **Cost gain** — best-of-N reliability at ~⅓ the calls; ties matched-cost pass-rate |
| Open-ended meta-task (research, review, design) | Hetero reflection: `create_reflection_engine` (or `create_quality_workflow_engine(..., mode="reflection")`) | ⚠️ **Conditional gain** — hetero reflection **10-0-0** vs single on meta+default (finding #7); lever is roster heterogeneity. Held-out source-grounded tasks showed no established superiority over a strong single call ([results](docs/findings.md#research-update-historical-findings-are-conditional)) |
| Self-contained reasoning (no tools, no verifier) | Strong single prompt or bigger model | The tested same-model scaffolds did not beat the tested strong single-call controls |

**Practical recipe for small models:**

1. **Explore / debug** — `agent_type="Explore"` + `tools=[...]`, optionally `isolation="worktree"`.
2. **Verifiable output** — `create_repair_engine(verifier=...)`; rotate `models=[small, small, medium]` on failure.
3. **Research / review / open-ended reflection** — try `create_reflection_engine(problem)` (reference pattern; conditional evidence, compare against a strong single call) with a heterogeneous roster (default `qwen` + `glm` via cliproxy). Do **not** default to adversarial/dialectic modes — finding #7 found no consistent lift over hetero reflection.
4. **Cost control** — `Workflow(..., budget_unit="tokens")`; use a small model for fan-out, a larger one only for synthesis or the last repair attempt.

`parallel` and concurrency caps control scheduling and can reduce wall-clock
time. Any quality benefit from additional samples or interaction requires a
separate comparison. Context caching (below) saves tokens on
multi-turn **tool loops inside one `agent()` call** — not across independent
`agent()` stages unless you share session state yourself.

### 🛠️ Execution-guided repair — verifier-in-the-loop (`create_repair_engine`)
For verifiable tasks: **generate → run an injected verifier → repair against the
concrete failure → retry**, until it passes or attempts run out. Built on the
`Workflow` kernel — internally, each attempt is one `agent(model=..., label=...)`
call in a bounded retry loop, no bespoke agent construction of its own.

- **Task-agnostic verifier** — any `Callable[[answer], (passed, feedback)]`: unit tests, a schema validator, a linter, assertion-checked logic. `solution_format` pins the output shape your verifier parses.
- **Uses the full failure history** — every prior attempt + its exact failure is fed back, so the loop doesn't oscillate between two wrong fixes.
- **Cost-disciplined** — short-circuits the moment the verifier passes, reaching best-of-N reliability at a fraction of the calls.
- **Multi-model** — pass `models=[...]` to rotate across a roster on failure; the per-attempt `history[i]["model"]` records which model produced each attempt.
- **Returns** `{final_answer, passed, attempts, history}`.

Measure it against pass@1 and matched-cost best-of-K — the measured verdict
(finding #2): beats a single call on pass-rate, ties matched-cost best-of-K,
at ~1/3 the calls.

## Patterns (not shipped, for reference)

`examples/patterns/` (a dev tool, like `evals/` — not packaged in the wheel)
holds runnable research patterns, including historical variants whose evals
did not justify shipping and new mechanisms still awaiting evidence. The demoted engines keep their exact
factory name/signature/return-shape, rebuilt on the `Workflow` kernel instead
of bespoke agent construction. (The `evals/*.py` scripts that originally
measured them were removed in the 2026-08 cleanup; their verdicts are recorded
in the table below and in [docs/findings.md](docs/findings.md).)

| Pattern | What it shows | Measured verdict |
|---|---|---|
| `agentic_pattern.py` (`create_agentic_engine`) | `agent(tools=[...], instructions=...)` as a standalone tool-using stage | Same 8/8 vs 0/8 win as the kernel primitive — kept only as a copy-pasteable recipe with the tailored system prompt, not because the capability needs a class. |
| `dialectic_pattern.py` (`create_dialectic_engine`) | thesis → antithesis → synthesis spiral, scored via `agent(schema=Verdict)` | Ties/loses a prompt-matched single call (**0-3-2**) on self-contained tasks, but **beats one on open-ended meta-tasks when tuned** (sharpened synthesis + `max_rounds=5`: **−0.500 → +0.600 NET**, finding #9). |
| `ensemble_pattern.py` (`create_ensemble_engine`) | AB-MCTS-lite adaptive search (Thompson-sampling bandit) over a heterogeneous roster | **CUT** by the honesty gate — a blind-pick roster (scorer replaced by a constant) matched the real scorer's robustness gain; the signal adds nothing over heterogeneity alone. |
| `reflection_pattern.py` (`create_reflection_engine`) | **Canonical** open-ended recipe: hetero gather → frame → critique → synthesize on `Workflow`. Opt-in `use_access_lists=True` routes critique/synthesize prior context through the kernel `sees=` primitive (Fugu-Ultra-style selective visibility) instead of inlining via `.format()`. | ⚠️ Conditional win — **5-0-0** vs single/homo on meta (finding #6); **10-0-0** vs single on meta+default via quality ablation (finding #7). No LLM scorer / AB-MCTS. Access-list mode is opt-in; the measured numbers above used inlined prompts. |
| `quality_workflow_pattern.py` (`create_quality_workflow_engine`) | Mode switcher over the same roster: `reflection` (default, delegates to reflection_pattern) / `adversarial` / `dialectic` | Ablation harness — adversarial/dialectic add no consistent lift over hetero reflection (finding #7). Prefer `create_reflection_engine` unless comparing modes. |
| `tot_gan_pattern.py` (`create_engine`/`create_coordinator`) | beam search + GAN-style adversarial refinement, `parallel()` for sibling expand/evaluate | **Measured dominated** — never wins a matchup against single/best-of-N/self-refine at matched compute; loses to a single call on Game-of-24 at ~34× the cost. |
| `claim_falsification_pattern.py` (`create_claim_falsification_engine`) | CLR-inspired independent claim assessment + weighted candidate selection | **Experimental** — repeated held-out comparisons (K=6, K=3) showed no selection benefit or established quality advantage; not promoted. |
| `meta_reasoning_pattern.py` (`create_meta_reasoning_engine`) | Staged/direct controllers, selective context, stored-artifact selection | **Experimental** — all differences against single retained zero on held-out meta budgets 6 and 12. |
| `self_refine_pattern.py` (`create_self_refine_engine`) | Iterative self-refinement with configurable selection policy (`last`, `plurality`, `convergence`, custom `selector`) | **Measured** — unguided `last` ties single (2/16 vs 2/16), but oracle-free checkers rescue lost intermediate solutions (9/16, 100% coverage); `convergence` early stopping saves ~62% of steps. |

Each pattern's docstring cites its exact eval verdict. They're written in the
kernel's own compositional idiom (plain functions/closures over
`agent()`/`parallel()`), not the original Protocol-based plugin system —
kept for study and historical-number reproducibility, not for extension.
Import them the same way the evals do:

```python
from examples.patterns.agentic_pattern import create_agentic_engine
from examples.patterns.dialectic_pattern import create_dialectic_engine
from examples.patterns.ensemble_pattern import create_ensemble_engine
from examples.patterns.reflection_pattern import create_reflection_engine
from examples.patterns.quality_workflow_pattern import create_quality_workflow_engine
from examples.patterns.tot_gan_pattern import create_engine
from examples.patterns.claim_falsification_pattern import (
    create_claim_falsification_engine,
)
from examples.patterns.meta_reasoning_pattern import create_meta_reasoning_engine
from examples.patterns.self_refine_pattern import create_self_refine_engine
```

## Evaluation

Does the engine actually beat a single strong-model call? The repo ships an
eval harness (`evals/`, a dev tool — not part of the published package) that
answers this with data: each problem is solved by the engine **and** by a
single-call baseline; a **blind judge** compares both answers twice with
positions swapped (historical disagreement = tie; new protocols preserve
inconclusive outcomes). New per-arm receipts include tokens, observable turns,
failures and raw records; harnesses save configuration, task text,
source/dependency fingerprints and analysis rules before the first model call,
so experiment paths cannot be reused.

| Script | Purpose |
|---|---|
| `uv run python -m evals.reflection_ablation` | reflection pattern: hetero vs homo vs single (open-ended) |
| `uv run python -m evals.quality_workflow_ablation` | multi-model modes vs single (meta+default, 10 problems) |
| `uv run python -m evals.workflow_ablation` | homogeneous reflection vs single (open-ended) |
| `uv run python -m evals.claim_ablation --help` | claim-falsification vs consensus/self-refine (objective verifier) |
| `uv run python -m evals.meta_ablation --help` | meta-reasoning controllers vs single (objective verifier) |
| `uv run python -m evals.evidence_ablation --help` | evidence-grounded decisions; generation, calibration and judging metered separately |
| `uv run python -m evals.research_campaign --help` | frozen repeated held-out campaign (no adaptive tuning or restart) |
| `uv run python -m evals.objective_analysis results.json --output analysis.json` | analyze completed objective-verifier reports |
| `uv run python -m evals.evidence_analysis evidence.json --output evidence.analysis.json` | analyze completed evidence-grounded reports |

`objective_analysis` averages repeats within each task and resamples paired tasks;
failed generation stays in the reliability denominator, unknown usage prevents
complete reported-cost claims, and missing pairs, duplicate trials or
inconsistent task pools fail analysis. Frozen source/rule drift is rejected
unless `--exploratory-reanalysis` records it. `evidence_analysis` compares each
arm with every declared single-model baseline, keeps unresolved preferences at
bounds of [-1, +1] and reports task-cluster uncertainty. Intervals are
exploratory and unadjusted for multiple comparisons.

The historical eval scripts (the ToT+GAN `python -m evals` CLI, and the
`repair_ablation` / `agentic_eval` / `quality_ablation` / `ensemble_ablation` /
`ensemble_meta_ablation` / `access_list_scale` / `scaffold_boundary` suites)
were removed in the 2026-08 cleanup; their findings are retained as a record.

### Results at a glance

Full methodology, numbers and caveats live in
[docs/findings.md](docs/findings.md). These are historical observations on the
tested tasks, models and protocols — not universal laws.

| # | Finding |
|---|---|
| 1 | **Tools add capability:** small model + `agent(tools=...)` 8/8 vs single call 0/8 on hidden-oracle. |
| 2 | **Pure-LLM scaffolds tied strong single calls on self-contained tasks;** repair beats a single call, ties matched-cost best-of-K at ~1/3 the calls. |
| 3 | **ToT+GAN was dominated:** Game-of-24 14/15 vs single 15/15 at ~34× the cost. |
| 4 | **No headroom** on the hardest Game-of-24 puzzles across four model tiers (single 5/5 everywhere). |
| 5 | **Ensemble scorer CUT:** the open-ended gain came from roster heterogeneity, not the scorer's ranking. |
| 6 | **Hetero reflection** beat single and homo reflection **5-0-0** on meta-tasks. |
| 7 | **Quality modes (10 problems):** hetero reflection 10-0-0 vs single; adversarial/dialectic add no consistent extra lift. |
| 8 | **Access lists** (`sees=`) shipped as a kernel primitive; reflection integration stays opt-in. |
| 9 | **Tuned dialectic** moved from −0.500 to +0.600 NET vs single on 3 meta tasks (single judge). |

#### Held-out campaign (2026-10-04)

The [frozen seven-study campaign](docs/research/2026-10-04-heldout-protocol.md)
screened 32 primary-source papers ([literature matrix](docs/research/2026-10-03-literature.md))
and ran 576 generation trials: **3,631,216 reported tokens / 3,789 observable
model turns** including calibration and judging, with **30 failed generations
retained**. These are reported costs, not provider billing or hidden HTTP request
counts. See the [completion audit](docs/research/2026-10-04-completion-audit.md)
and [raw-record integrity audit](docs/research/results/2026-10-04-heldout-v1/final-integrity-audit.json).

| Held-out comparison | Observed result | Adoption decision |
|---|---|---|
| [Source-grounded decisions](docs/research/2026-10-04-heldout-evidence-result.md) | Exploratory positive panel signals for self-refinement vs Gemini single and heterogeneous reflection vs Qwen single; no established superiority vs GPT single | Keep reflection as a reference pattern; synthetic quote validity and panel agreement do not prove decision correctness or human alignment |
| [Claims K=6](docs/research/2026-10-04-heldout-claims-k6-result.md) | Claims 6/24; consensus/self-refinement 7/24; single 4/24 | Claims-versus-single interval retains zero; no stable API promotion |
| [Claims K=3](docs/research/2026-10-04-heldout-claims-k3-result.md) | Claims/self-refinement 7/24; single/consensus 3/24 | Claims-versus-single interval retains zero; no stable API promotion |
| [Meta budget 12](docs/research/2026-10-04-heldout-meta-budget12-result.md) | Single 5/24; consensus 3/24; self-refinement 8/24; staged 2/24; direct 3/24 | All differences against single retain zero; controllers remain research modes |
| [Meta budget 6](docs/research/2026-10-04-heldout-meta-budget6-result.md) | Single 5/24; consensus 4/24; self-refinement 10/24; staged 4/24; direct 0/24 | All differences against single retain zero; favorable self-refinement point estimates are insufficient for adoption |
| Strong single controls: [meta](docs/research/2026-10-04-heldout-strong-meta-result.md) / [claims](docs/research/2026-10-04-heldout-strong-claim-result.md) | GPT 24/24 under each output contract | Observed ceilings on this pool, not universal success or tests of mechanisms on GPT |

Post-hoc [selection diagnostics](docs/research/2026-10-04-heldout-selection-diagnostics.md)
guide future research, not retuning on the frozen pool. Intervals condition on
small task pools, are exploratory without multiplicity correction, and token
costs are unequal. **The shipped surface remains Workflow and verifier-guided
repair; new superiority claims require strong prompt-matched controls, complete
per-arm cost receipts, held-out tasks, repetitions and reliable evaluation —
E2E proves execution only.**

## Configuration

All config is read from `os.environ` — as a library, Dialectica does **not**
load `.env` itself; the consuming app owns environment setup. Only the test
suite loads `dialectica/.env`.

```bash
# Default model for all agents
export DEFAULT_MODEL_CONFIG="google:gemini-3.5-flash"

# Role-specific override (optional) — every wf.agent() call uses the Generator role
export GENERATOR_MODEL_CONFIG="google:gemini-3.5-flash"
# Used by evals/judge.py's blind judge, not by any shipped engine
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

### Runtime variables (all optional)

| Variable | Default | Effect |
|---|---|---|
| `DIALECTICA_CONTEXT_CACHE` | off | Gemini context cache via ADK App (`true` to enable) |
| `DIALECTICA_CONTEXT_CACHE_INTERVALS` | `10` | cache intervals |
| `DIALECTICA_CONTEXT_CACHE_TTL_SECONDS` | `1800` | cache TTL |
| `DIALECTICA_CONTEXT_CACHE_MIN_TOKENS` | `4096` | Gemini hard floor |
| `DIALECTICA_CONTEXT_CACHE_CREATE_TIMEOUT_MS` | unset | `CachedContent.create()` timeout |
| `DIALECTICA_ADK_TELEMETRY` | off | OpenTelemetry (or set `OTEL_EXPORTER_OTLP_*` instead) |
| `DIALECTICA_TOOL_WORKERS` | unset | positive int; offload blocking sync tools to ADK's thread pool |
| `DIALECTICA_MAX_LLM_CALLS` | ADK limit | positive int; bounds each ADK invocation's tool loop |
| `DIALECTICA_WORKFLOW_CONCURRENCY` | `min(16, cpu−2)` | cap on overlapping `agent()` calls; `Workflow(concurrency=...)` takes precedence |
| `DIALECTICA_MAX_CONCURRENCY` | unlimited | global cap on overlapping `run_agent()` calls |
| `DIALECTICA_WORKFLOW_JOURNAL_DIR` | `.dialectica/workflows` | where resume journals are written |

### Runtime behavior

The runtime targets [ADK 2.11](https://github.com/google/adk-python/releases/tag/v2.11.0).
`tools` and `schema` can be used together: ADK selects native structured output
or its response-tool fallback from the model's declared capabilities. Provider
support still varies; the offline suite covers both ADK paths, not every hosted
model. A runner stays open across transport retries, with a fresh session per attempt,
and closes its toolsets and plugins once after overall success, failure or task
cancellation. Task cancellation propagates without retry. Invalid requests,
authentication failures, missing models and explicit expired-subscription or
billing-quota errors fail immediately; transient network/capacity errors retry.

Journals store per-step reported usage, including successful structured-output
re-asks. Parallel steps reserve unique positions before model calls and replay
in invocation order; cached labeled results restore `sees=` context. Changed
suffixes replace stale entries. Legacy journals with duplicate parallel positions
are recomputed on resume. Cached replay incurs no new token budget charges;
ADK model callbacks capture reported tokens before event creation, so failed
attempts are included in retry totals and final exceptions expose
`dialectica_usage`. Failed steps are journaled but never replayed as successful
results. Append-only `usage.jsonl` receipts retain usage when resume replaces
cache entries. `TokenUsage.unknown_calls` marks model attempts without a final
usage report; interrupted partial reports are retained and replaced by a final
cumulative report when available, avoiding double counting; reported totals are partial when it is nonzero, not a claim of
zero billing.

`TokenUsage.model_calls` counts ADK model turns observed before dispatch,
including runtime retries, tool-loop turns and cache short circuits. It is
recorded in budgets, journals and experiment receipts; workflow `spent_calls()`
still counts agent steps. SDK and provider-internal retries remain outside this
counter, so it does not establish exact HTTP request or billing counts. Old
journals lacking the field remain readable; their default zero means the
counter was not recorded. A `tokens` budget caps reported output tokens,
including reported thinking; input/total/cached usage is recorded separately.

Explicit model configuration fails before dispatch for malformed values,
unsupported providers or missing OpenAI/OpenRouter credentials; it never
silently selects a Google model. Use `provider:model` (`openrouter:vendor/model`
routes through OpenRouter) and unset `DEFAULT_MODEL_CONFIG` to choose the native
default.

Leave `DIALECTICA_TOOL_WORKERS` unset for tools that depend on the calling
thread; Python cannot stop a sync tool already running in a worker thread. Both
`DIALECTICA_TOOL_WORKERS` and `DIALECTICA_MAX_LLM_CALLS` require positive
integers. `DIALECTICA_MAX_LLM_CALLS` overrides native `ADK_MAX_LLM_CALLS` when
set; otherwise ADK resolves its own limit (500 per invocation if unset). Reaching
it fails without restarting the tool loop and is separate from the outer
Workflow budget, which counts `agent()` steps or reported tokens.

Install reproducibly with `uv sync --locked`. [The dependency audit](docs/research/2026-10-04-dependency-audit.md)
separates the frozen experimental environment from the final installed one and
explains the transitive pins that prevent absolute-latest versions.

Known-good Gemini ids are `gemini-3.5-flash` (default) and `gemini-3.1-pro-preview`
(there is no stable `gemini-3.1-pro`; see [Troubleshooting](#troubleshooting)). Provider strings are
`provider:model_name`; the `openai:` provider passes `api_base` explicitly
(recent LiteLLM no longer reads `OPENAI_API_BASE` for the `openai/` prefix).

### Parameters

- **`agent()`** — see the signature under [Workflow kernel](#workflow-kernel--repair).
- **`Workflow`** — `budget_total` / `budget_unit` (`"calls"` or `"tokens"`), `resume_run_id`, `meta`, `concurrency`; `budget().usage()` includes `cached_tokens` when the backend reports cache hits.
- **`create_repair_engine`** — `verifier` (mandatory), `max_attempts`, `solution_format`, `models` (optional roster).
- **Patterns** — see each pattern's own docstring/factory signature in `examples/patterns/`; they keep their demoted engine's original parameters (e.g. `scorer`/`policy` for the ensemble pattern, `criteria`/`rounds` for the dialectic pattern).

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

### Tool-using stage (kernel primitive)

```python
from dialectica import Workflow, agent


async def script():
    return await agent("Fix the failing test", tools=[read_file, run_tests])


result = await Workflow(script).run()  # tools do the acting; check the outcome after
```

### Patterns (illustrative only — not shipped API)

Open-ended meta-tasks — canonical hetero reflection (finding #6 / #7):

```python
from examples.patterns.reflection_pattern import create_reflection_engine

engine = create_reflection_engine(
    "Design the pricing tier",
    # default roster: openai:qwen3.6-flash + openai:glm-5.2
    # use_access_lists=True  # route prior context through sees= instead of inlining
)
result = await engine.run()
# {"final_answer", "history", "heterogeneous"}
```

Ensemble + float scorer is **CUT** (finding #5) — kept only for historical
ablation; prefer reflection above for open-ended quality.

### Inspecting the result

`create_repair_engine` and every pattern in `examples/patterns/` return a
`dict` with `final_answer` plus a trace (`history` / `attempts`). Repair and
ensemble-pattern `history` entries carry the producing model per attempt;
reflection `history` records stage, label, and model.

## Development

```bash
uv sync                                         # install deps
uv run pytest                                   # mocked, fast, no API key
uv run pytest -m e2e                            # live repair + tools/schema/worker tests (configured model credentials)
uv run pytest -m e2e_access                     # live access-list tests (needs OPENAI_API_BASE + OPENAI_API_KEY + DEFAULT_MODEL_CONFIG=openai:...)
uv run pytest -m 'e2e or e2e_access'             # all live cases via a configured OpenAI-compatible backend
uv run ruff format && uv run ruff check         # format / lint
```

For cliproxy, load your shell environment, map `CLIPROXYAPI_BASE_URL` (including
`/v1`) to `OPENAI_API_BASE` and `CLIPROXYAPI_TOKEN` to `OPENAI_API_KEY`, then set
`DEFAULT_MODEL_CONFIG` and `GENERATOR_MODEL_CONFIG` to an available `openai:`
model and `DIALECTICA_DISABLE_THINKING=true` for Qwen. Set
`E2E_REFLECTION_FAST_MODEL` and `E2E_REFLECTION_STRONG_MODEL` to two distinct
available model configs; their historical defaults are Qwen 3.6 Flash and GLM 5.2.
The tool/schema tests retrieve a random value absent from the prompt, validate
the result, check the actual sync tool thread, and require backend-reported
token usage. Missing credentials cause skips; a skipped case is not live acceptance.

Dated live-acceptance snapshots (pass counts, timings, rosters) are recorded in
[docs/findings.md](docs/findings.md#live-verification-snapshots) and the
[completion audit](docs/research/2026-10-04-completion-audit.md); they establish
execution, not quality superiority.

The library never calls `logging.basicConfig` — the consuming app owns logging.
Mock the LLM at the single seam `agent_runtime.run_agent()` — never patch ADK
internals or per-stage agents (`tests/helpers.py` has the fakes). `asyncio_mode =
auto`; pytest-bdd steps are sync, so wrap coroutines with `asyncio.run()`.
The `examples/patterns/` reference scripts get a lighter regression net
(`tests/test_example_patterns_smoke.py`, one mocked end-to-end run each) —
full BDD scenario coverage is reserved for the shipped kernel + repair.

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
  adk_config.py          # ADK cache, tool workers, call limits + OpenTelemetry
  agent_factory.py       # builds LlmAgents from ROLE_TEMPLATES (Generator only)
  agent_runtime.py       # THE single LLM seam: run_agent() + retry/backoff
  json_repair.py         # shared fence/escape JSON-repair helpers
  llm_config.py          # provider:model parsing (google/openrouter/openai)
  repair.py              # create_repair_engine (cost win)
  workflow.py            # Workflow + agent/parallel/pipeline/phase/log/budget + sees= access lists (the kernel)
  workflow_journal.py    # run journal + resume (.dialectica/workflows/<run_id>/)
  workflow_registry.py   # register_workflow named registry
  workflow_worktree.py   # agent(isolation="worktree")
examples/patterns/       # reference implementations (not shipped)
  agentic_pattern.py, dialectic_pattern.py, ensemble_pattern.py, tot_gan_pattern.py  # demoted engines
  reflection_pattern.py       # canonical open-ended recipe (hetero); opt-in use_access_lists
  quality_workflow_pattern.py # mode ablation switcher
  claim_falsification_pattern.py, meta_reasoning_pattern.py  # experimental research modes
  self_refine_pattern.py      # self-refinement with convergence & selection policies
  _scoring.py                 # shared Verdict schema
evals/                   # dev-only eval harness (not shipped in the wheel)
  baseline.py, harness.py, judge.py, problems.py, meta_problems.py  # shared primitives
  reflection_ablation.py, workflow_ablation.py, quality_workflow_ablation.py  # open-ended ablations
  claim_ablation.py, meta_ablation.py, research_ablation.py, evidence_ablation.py, research_campaign.py  # held-out research
  selection_study.py, selection_rules.py  # candidate trajectory selection research
  evidence_eval.py, evidence_tasks.py, research_tasks.py  # task pools + evidence judge
  measurement.py, experiment_protocol.py, objective_analysis.py, evidence_analysis.py  # receipts, freezing, analysis
docs/
  findings.md            # measured findings, research update, live-verification snapshots
  research/              # literature matrix, protocols, held-out results, audits
tests/                   # BDD features + step defs + helpers
```

## Troubleshooting

- **`gemini-3.1-pro` 404s** — use `gemini-3.1-pro-preview` or `gemini-3.5-flash`.
- **OpenAI-compatible backend "Connection error"** — `OPENAI_API_BASE` is no longer read for the `openai/` prefix by recent LiteLLM; the library passes `api_base` explicitly, so make sure `OPENAI_API_BASE` is set (not just `OPENAI_API_KEY`).
- **`ValueError` before any model call** — explicit model config is validated up front: use `provider:model`, a supported provider (`google`, `openrouter`, `openai`) and that provider's credentials.
- **Tool loop stops with an ADK call-limit error** — `DIALECTICA_MAX_LLM_CALLS` (or `ADK_MAX_LLM_CALLS`) was reached; the loop is not restarted. Raise the limit or tighten the task.
- **E2E tests report skipped** — credentials were missing; a skipped case is not live acceptance.
- **qwen-family evals are slow** — set `DIALECTICA_DISABLE_THINKING=true` to disable the reasoning trace (`chat_template_kwargs.enable_thinking=false`).
- **Ensemble pattern roster "collapsed to duplicate effective model"** (`examples/patterns/ensemble_pattern.py`) — this pattern no longer warns automatically (the check needed pre-built agents, dropped when it was demoted); compare your `models` list for duplicates yourself before calling `create_ensemble_engine`.
- **ToT+GAN pattern + enforced JSON mode returns empty verdicts** (some backends, e.g. gemma-4-26b-a4b) — the pattern's `structured_output` parameter is accepted for signature parity but always uses schema-enforced scoring; the original engine's workaround was not ported.

## Migration from 0.6.x

`create_agentic_engine`, `create_ensemble_engine`, `create_dialectic_engine`,
`create_engine`/`create_coordinator` and their supporting `Protocol`/model
types are **no longer part of the public API**. They remain available as
unshipped reference implementations in `examples/patterns/` (not installed
via `pip install dialectica`):

```python
# before (0.6.x)
from dialectica import create_agentic_engine

# after (0.7.0) — same signature/return-shape, now unshipped reference code
from examples.patterns.agentic_pattern import create_agentic_engine
```

Or, for the tool-using case specifically, use the kernel primitive directly —
no separate import needed:

```python
from dialectica import Workflow, agent

result = await Workflow(lambda: agent(task, tools=[...])).run()
```

`create_repair_engine`'s signature and return shape are unchanged.
`workflow.agent()` gained `instructions=` (task-specific system-prompt
framing), now correctly resolves `provider:model`-style `model=` overrides
(previously passed through unresolved), and gained `sees=` (a per-step
access list for selective context visibility — Fugu-Ultra-inspired
anti-collapse; opt-in, default unchanged). `dialectica.gan_evaluator`
is renamed `dialectica.json_repair` (only the shared fence/escape helpers
survive; the GAN-specific classes moved to `examples/patterns/tot_gan_pattern.py`).

## Contributing

Conventional commits. Release = push a `v*.*.*`
tag whose version **matches** `pyproject.toml`; CI runs tests, publishes to PyPI,
and creates a GitHub release. When adding to the shipped API, ship the
honesty-gate ablation that would CUT it if the data says so — the repo's
tradition is documented negative results, not unproven claims. This release's
own honesty gate is the reason the shipped surface is now just the kernel and
repair — see [Patterns](#patterns-not-shipped-for-reference).

## License

MIT — see `LICENSE`.

## References

- [Tree of Thoughts](https://arxiv.org/abs/2305.10601) — Yao et al., 2023 (the ToT+GAN pattern's lineage; now reference-only).
- [Sakana AB-MCTS / "Wider or Deeper?"](https://arxiv.org/abs/2503.04412) — the ensemble pattern's lineage (independence + ground-truth signal).
- [Sakana Fugu](https://sakana.ai/fugu/) — the multi-model coordinator whose per-step access-list mechanism inspired the kernel's `sees=` primitive (finding #8).
- [Claim-level falsification (CLR)](https://arxiv.org/abs/2608.11994) and [structured meta-reasoning](https://arxiv.org/abs/2609.38147) — the lineage of `claim_falsification_pattern.py` and `meta_reasoning_pattern.py`; authors' results, not local replications. Local screening is in the [literature matrix](docs/research/2026-10-03-literature.md).
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — inspiration.

## Acknowledgments

Built on Google ADK. The honesty-gate methodology owes to the blind
position-swapped judge pattern used across LLM evals.
