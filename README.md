# Dialectica ![](https://img.shields.io/badge/A%20FRAD%20PRODUCT-WIP-yellow)

[![PyPI](https://img.shields.io/pypi/v/dialectica.svg)](https://pypi.org/project/dialectica/) [![Twitter Follow](https://img.shields.io/twitter/follow/FradSer?style=social)](https://twitter.com/FradSer) [![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![Framework](https://img.shields.io/badge/Framework-ADK%202.1-orange.svg)](https://google.github.io/adk-docs/) [![Evaluation](https://img.shields.io/badge/Evaluation-GAN%20Adversarial-purple.svg)]()

English | [简体中文](https://github.com/FradSer/dialectica/blob/main/README.zh-CN.md)

**Dialectica** is a reasoning-engine toolbox on Google ADK, **led by an execution-guided repair engine**: generate → run an objective verifier → repair against the concrete failure → retry. That loop is the one engine here that *structurally* beats a single strong-model call — because it adds ground-truth verification a single forward pass cannot. It also ships a **dialectic** engine (*thesis → antithesis → synthesis*) for transparent, criteria-steered open-ended reasoning, and a legacy **Tree-of-Thoughts + GAN** pipeline as a baseline. Every stage is a swappable component. Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) and Claude Code's composable workflows.

> **Honest scope (measured — see [Evaluation](#evaluation)).** On self-contained tasks, pure-LLM scaffolds (ToT, dialectic) do **not** beat a prompt-matched single call on result quality — they only rearrange the model's own thinking, adding no information (controlled test: dialectic 0-3-2 vs a prompt-matched call). The genuine, measured wins are narrower and real: **repair beats a single call and is cheaper than matched-cost best-of-K** (it short-circuits on success — e.g. 5 vs 12 calls at equal pass-rate), and the dialectic's value is an **auditable** reasoning trace, not better answers. For breadth/scale, use a workflow and call these engines per node. Reproduce the numbers with `uv run python -m evals.repair_ablation`.

## Install

Use it as a library in your own project:

```bash
uv add dialectica
# or: pip install dialectica
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
open-ended reasoning with an auditable trace, use `create_dialectic_engine`;
the legacy `create_engine` (Tree-of-Thoughts + GAN) is kept as a baseline. The
library reads configuration from `os.environ` and does **not** load `.env`
itself. To work on Dialectica instead, see [Development](#development).

## Key Features

### 🛠️ Execution-guided repair — the core (`create_repair_engine`)
The one engine that *structurally* beats a single call, because it acts on
ground truth: **generate → run an injected verifier → repair against the
concrete failure → retry**, until it passes or attempts run out.

- **Task-agnostic verifier** — any `Callable[[answer], (passed, feedback)]`: unit tests, a schema validator, a linter, assertion-checked logic. `solution_format` pins the output shape your verifier parses.
- **Uses the full failure history** — every prior attempt + its exact failure is fed back, so the loop doesn't oscillate between two wrong fixes.
- **Cost-disciplined** — short-circuits the moment the verifier passes (cheaper than best-of-K at equal reliability), and stops early if an attempt repeats a prior solution (no-progress).
- **Returns** `{final_answer, passed, attempts, history}`.

Measure it honestly against pass@1 and matched-cost best-of-K with
`uv run python -m evals.repair_ablation`.

The two engines below are pure-LLM scaffolds: useful for transparency/steering, but (measured) **not** a result-quality win over a single call — see [Honest scope](#dialectica-) and [Evaluation](#evaluation).

### 🧩 Pluggable engine (thesis → antithesis → synthesis)
The `Engine` owns only the search *control flow*; every decision is delegated to
an injected component, so any stage can be swapped without touching the engine:

| Stage | Role | Default |
|-------|------|---------|
| `Generator` | propose thoughts (**thesis**) | `LlmGenerator` |
| `Evaluator` | critique & refine (**antithesis**) | `AdversarialEvaluator` |
| `Selector` | choose the frontier | `BeamSearch` |
| `Synthesizer` | combine into an answer (**synthesis**) | `LlmSynthesizer` |

Retarget it at code review, research, or decision-making just by changing the
generator's prompts or swapping a stage — see [Pluggable Architecture](#pluggable-architecture).

### 🔄 GAN-style adversarial evaluation (keep-best)
Each thought undergoes **iterative adversarial refinement** rather than a single pass:
1. **Discriminator** scores it with a structured verdict (score, flaws, suggestions)
2. **Generator** refines it from that critique
3. **Discriminator** re-scores
4. Loop until the quality threshold, a terminate signal, or `max_gan_rounds`

Refinement is **not assumed monotonic** — the loop keeps the *best-scoring* round
(à la autoresearch's "keep only what beats the current best"), and the node stores
that refined text so synthesis works on the improved version, not the original.

### 🌳 Tree search with merit-based beam
- **Strategies are scored before the beam** — the frontier reflects merit, not generation order
- **Beam search** keeps the top-k most promising paths (`BeamSearch`, or `GreedySearch`)
- **Pruning**: paths below threshold are dropped; exploration stops when the beam empties
- **Multi-node synthesis**: the final answer integrates the top scoring thoughts across branches

### 📊 Structured evaluation results
The `Discriminator` returns a `DiscriminatorVerdict` via ADK `output_schema` (no
fragile text parsing). The engine wraps it as an `EvaluationResult`:
`score`, `flaws`, `suggestions`, `should_terminate`, `reasoning`,
`adversarial_rounds`, `refined_thought`, and the full per-round `history`.

## Architecture

```
User Problem
    ↓
Engine — Phase 1: Initialize
    ↓
Generator expands root → initial strategies
    ↓ (each strategy scored by the Evaluator before it can enter the beam)
Engine — Phase 2: Explore (beam search)
    ↓
For each node in the Selector's frontier:
    ├── Generator expands it into children
    └── for each child, Evaluator runs the GAN loop:
        ├── Discriminator scores (structured verdict)
        ├── Generator refines from the critique
        ├── re-score, keep the best round
        └── persist the refined thought + score on the node
    → children ≥ threshold form the next beam
    ↓
Engine — Phase 3: Synthesize
    ↓
Synthesizer integrates the top thoughts
    ↓
Final Answer (+ thought_tree, best_path, stats)
```

## Workflow Phases

### Phase 1: Initialization
- Creates the root node from the user problem
- `Generator.expand(root)` produces the initial strategies (validated via `ThoughtData`)
- **Each strategy is adversarially scored**, then the ones clearing the threshold seed the beam (falling back to the Selector's top-k if none clear it)

### Phase 2: Exploration (beam search)
Iterates up to `max_depth` times:
1. **Select**: `Selector.select(...)` picks the frontier from the active beam
2. **Generate**: `Generator.expand(parent)` creates child thoughts
3. **Evaluate**: `Evaluator.evaluate(...)` runs the GAN loop, keeping the best round and persisting the refined thought
4. **Filter**: children scoring ≥ `score_threshold` form the next beam

Exploration stops when the beam empties or `max_depth` is reached.

### Phase 3: Synthesis
- `Synthesizer.synthesize(...)` takes the top-scoring evaluated thoughts
- Produces a coherent, comprehensive final answer

## Relation to the Tree of Thoughts paper

How the default wiring maps onto [Yao et al. 2023](https://arxiv.org/abs/2305.10601):

| ToT paper concept | Dialectica |
|-------------------|------------|
| Thought decomposition | Generic two-level prompts: root → strategies, node → next steps (`generation.py` templates) — not per-task like the paper's |
| Thought generator `G(p, s, k)` — **propose** | `LlmGenerator`: one call proposes k distinct candidates (capped by `max_items`) |
| Thought generator — **sample** (k i.i.d. CoT samples) | Not built in; pluggable via a custom `Generator` |
| State evaluator `V(p, S)` — **value** (independent scalar) | The Discriminator's 0-10 structured verdict |
| State evaluator — **vote** (comparative) | Not built in; pluggable via a custom `Evaluator`/`Selector` |
| ToT-BFS with breadth limit `b` | `BeamSearch(width=b)`; `GreedySearch` is `b=1` |
| DFS pruning threshold `v_th` | `score_threshold` (children below it are pruned) |
| DFS + **backtracking** | Not implemented — when the beam empties, exploration stops instead of revisiting parents |
| Evaluator **lookahead** simulation | Not implemented (prompt-level gap) |

Deliberate extensions beyond the paper: the evaluator *refines* thoughts (the
GAN keep-best loop — the paper's evaluator never mutates state), and a final
`Synthesizer` integrates top thoughts across branches (the paper outputs the
best path).

## Development

To work on Dialectica itself (not needed just to *use* it — see [Install](#install)):

```bash
git clone https://github.com/FradSer/dialectica
cd dialectica
uv sync
cp .env.example dialectica/.env   # add GOOGLE_API_KEY for the live e2e test
```

Then run the suite — see [Testing](#testing).

## Configuration

### Environment Variables

**Model Configuration:**
```bash
# Default model for all agents
DEFAULT_MODEL_CONFIG=google:gemini-3.5-flash

# Role-specific overrides (optional)
GENERATOR_MODEL_CONFIG=google:gemini-3.1-pro-preview
DISCRIMINATOR_MODEL_CONFIG=google:gemini-3.1-pro-preview
SYNTHESIZER_MODEL_CONFIG=google:gemini-3.1-pro-preview
```

**Supported Providers:**
- `google:gemini-3.5-flash` (Google AI Studio)
- `openrouter:anthropic/claude-3.5-sonnet` (OpenRouter)
- `openai:gpt-4o` (OpenAI)

**API Credentials:**
```bash
# Google AI Studio
GOOGLE_API_KEY=your-key-here

# Or Vertex AI
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=us-central1

# OpenRouter
OPENROUTER_API_KEY=sk-or-...

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
```

### Engine Parameters

```python
engine = create_engine(
    problem="Your problem statement",
    max_depth=4,               # Max tree depth
    beam_width=3,              # Active paths per iteration
    max_gan_rounds=3,          # Max adversarial refinement rounds
    score_threshold=7.0,       # Min score to enter the beam
    gan_score_threshold=None,  # "Stop refining" bar (default: score_threshold)
    criteria=None,             # Discriminator rubric (default: feasibility-anchored)
    synthesizer_model=None,    # Optional model override
)
```

`criteria` deserves attention: the eval matrix showed the discriminator's
rubric steers answer *content*, not just selection (see
[Results](#results-2026-06)). The default rubric is feasibility-anchored;
pass your own to retarget the engine, e.g. a security-review rubric.

Sibling thoughts are expanded and evaluated **concurrently**, and the runtime
retries transient LLM failures with exponential backoff — a single network
error no longer destroys a long run.

## Usage Examples

### Basic Usage

```python
from dialectica import create_engine

# Create the engine
engine = create_engine(
    "Design a sustainable urban transport system"
)

# Run workflow
result = await engine.run()

# Access results
print(result["final_answer"])
print(f"Generated {len(result['thought_tree'])} thoughts")
print(f"Best path: {result['best_path']}")
```

### Inspecting the result

`run()` returns the answer plus the full search trace:

```python
result = await engine.run()
result["final_answer"]   # synthesized answer
result["best_path"]      # node ids from root to the highest-scoring thought
result["thought_tree"]   # every node, with scores and per-round GAN history
result["stats"]          # total_thoughts, max_depth_reached, duration_seconds
```

### Custom Configuration

```python
engine = create_engine(
    problem="Optimize supply chain logistics",
    max_depth=5,
    beam_width=5,
    max_gan_rounds=4,
    score_threshold=8.0,
    synthesizer_model="google:gemini-3.1-pro-preview",
)
```

## Project Structure

```
dialectica/
├── __init__.py           # Public API exports
├── agent.py              # Composition root: create_engine() wires defaults
├── coordinator.py        # Search engine — orchestrates the pluggable stages
├── protocols.py          # Stage interfaces: Generator/Evaluator/Selector/Synthesizer
├── generation.py         # LlmGenerator (default Generator) + list parsing
├── gan_evaluator.py      # AdversarialEvaluator / SinglePassEvaluator (Evaluator)
├── selection.py          # BeamSearch / GreedySearch (Selector)
├── synthesis.py          # LlmSynthesizer (default Synthesizer)
├── agent_runtime.py      # Single LLM-call seam (run_agent)
├── agent_factory.py      # Dynamic agent creation (role templates)
├── models.py             # ThoughtData, DiscriminatorVerdict, EvaluationResult
├── llm_config.py         # Model configuration factory
└── validation.py         # Thought validation utilities
tests/
├── conftest.py           # Loads .env for the e2e skip guard
├── helpers.py            # Deterministic mock LLM stand-ins
├── test_models.py        # Schema / verdict unit tests
├── test_generation.py    # List parsing + generator prompt routing
├── test_gan_evaluator.py # GAN loop + single-pass evaluator (mocked LLM)
├── test_coordinator.py   # Engine control flow (injected fake stages)
├── test_default_pipeline.py  # Default composition integration (mocked LLM)
├── test_eval_harness.py  # Eval harness units (judge normalization, counting, report)
├── test_e2e_live.py      # Real Gemini E2E (marked `e2e`)
└── test_eval_live.py     # Real Gemini eval-harness E2E (marked `e2e`)
evals/                     # Eval harness (dev tool, not shipped in the wheel)
├── problems.py            # Benchmark problems
├── baseline.py            # Single-call baseline (the control arm)
├── judge.py               # Blind pairwise judge with position-swap bias control
├── harness.py             # Orchestration, call counting, report rendering
└── __main__.py            # CLI: uv run python -m evals
```

## Testing

The suite has two tiers:

- **Mocked tests** (default) — fast, deterministic, no API key. They replace
  the LLM call seam with stand-ins and exercise the real orchestration: beam
  search, the GAN refinement loop, pruning, and synthesis.
- **Live E2E** (`@pytest.mark.e2e`) — drives the full workflow against the real
  Gemini API. Deselected by default and auto-skipped when `GOOGLE_API_KEY` is
  unset (loaded from `dialectica/.env`).

```bash
uv run pytest          # mocked tests only (seconds, no key)
uv run pytest -m e2e   # live API E2E (slower, requires GOOGLE_API_KEY)
```

## Evaluation

> **Headline finding (2026-06, measured, no preset conclusion).** Judged against a *matched-cost* baseline, **no pure-LLM scaffold here beats a single call on result quality**: the dialectic went **0-3-2** against a prompt-matched strong baseline (it ties/loses — the earlier 4-1-0 "win" was prompt + length, not structure). The **repair** engine beats a *single* call but exactly ties matched-cost best-of-K (across HumanEval, an original edge-case set, LeetCode-medium, LCB-hard, and a purpose-built uncontaminated benchmark, **feedback-only wins = 0** every time — even a weak model one-shots medium verifiable tasks, so the "fails-but-fixable" band is near-empty). Repair's real, measured edge is **cost at equal reliability** (it short-circuits: e.g. 5 vs 12 calls for the same pass-rate). Reproduce with `uv run python -m evals.repair_ablation` against the uncontaminated `evals/novel_problems.py`.

Does the engine actually beat a single strong-model call? The repo ships an
eval harness (`evals/`, a dev tool — not part of the published package) that
answers this with data instead of vibes:

1. Each benchmark problem (`evals/problems.py`) is solved by the **engine**
   and by a **single-call baseline** (one well-prompted LLM call).
2. A **blind judge** compares the two answers without knowing which is which.
   Position bias is neutralized by judging twice with swapped positions —
   if the two verdicts disagree, the comparison is a tie.
3. The report tallies wins and the cost of each arm (LLM calls, wall time),
   counted through the same `run_agent` seam the tests mock.

```bash
uv run python -m evals                          # all benchmark problems
uv run python -m evals --limit 2 --json out.json
uv run python -m evals --max-depth 3 --beam-width 3 --gan-rounds 2
```

Model overrides via env: `BASELINE_MODEL_CONFIG` and `JUDGE_MODEL_CONFIG`
(same `provider:model_name` format; e.g. point the baseline at
`google:gemini-3.1-pro-preview` to compare against a stronger single call).

### Results (2026-06)

Three full matrix runs on the 5 default benchmark problems, all judged blind
by `gemini-3.5-flash` with position-swap bias control (engine config:
`max_depth=2, beam_width=2, max_gan_rounds=2, threshold=7.0`). Between V1 and
V2 exactly one thing changed: the discriminator's **"Innovation"** criterion
was replaced with **"Feasibility under stated constraints"** — making the
matrix a controlled test of how the adversarial criteria steer answers. V3 is
a second seed of the V2 criteria, run after hardening the engine with
concurrent evaluation and verdict retry.

| Matrix | Criteria | engine(flash) vs flash | engine(flash) vs **pro** | engine(qwen) vs qwen | Total (W-L-T) |
|--------|----------|------------------------|--------------------------|----------------------|---------------|
| V1 | Innovation | 2-1-2 | 3-2-0 | 2-2-1 | 7-5-3 |
| V2 | Feasibility | 4-1-0 | 4-1-0 | 3-2-0 | **11-4-0** |
| V3 | Feasibility (seed 2) | 2-2-1 | 3-2-0 | **4-0-1** | 9-4-2 |

Per-problem detail for the controlled V1 → V2 comparison:

| Problem | engine(flash) vs flash | engine(flash) vs **pro** | engine(qwen) vs qwen |
|---------|------------------------|--------------------------|----------------------|
| cloud-costs | tie → engine | engine → engine | engine → baseline |
| api-versioning | engine → engine | engine → engine | baseline → engine |
| flaky-tests | engine → engine | engine → engine | engine → engine |
| meeting-overload | tie → baseline | baseline → engine | baseline → baseline |
| urban-transport | baseline → engine | baseline → baseline | tie → engine |

flash = `gemini-3.5-flash` · pro = `gemini-3.1-pro-preview` (single call) ·
qwen = `qwen3.6-35b-a3b`. Engine cost: ~20× LLM calls vs the baseline's 1 on
Gemini, ~30× on Qwen (a stricter discriminator triggers more GAN rounds).

What the 45 comparisons say:

- **The criteria are a steering knob, not just a filter.** Swapping one
  evaluation criterion moved the record from 7-5-3 (V1) to a pooled
  **20-8-2** (V2+V3). Because the GAN loop *refines* thoughts against the
  critique (unlike a pure value function), whatever the discriminator
  rewards gets written into the final answer.
- **Technical/engineering problems: the engine wins reliably** — 7-1-1 under
  V1, **15-2-1** pooled under feasibility criteria (cloud costs, API
  versioning, flaky-test remediation). Judges credit refinement-produced
  depth: contract-testing pipelines, correct HTTP semantics for brownouts
  (503 vs 410), rollback procedures and stabilization windows before
  financial commitments.
- **Organizational/social problems went from losing to roughly even** —
  0-4-2 under V1 (consistently judged "over-complex, impractical", across
  both model families) to 5-6-1 pooled under feasibility criteria. Still the
  engine's weak spot, with visible seed-to-seed variance.
- A flash engine beats a single stronger **pro** call 7-3 pooled — search
  can buy back model-tier quality, at ~20× the calls.
- **Concurrency cut wall-clock 2-3×** at unchanged call counts: 64-108
  s/problem on Gemini in V3 (vs 143-228 s sequential in V2), 272-314 s on
  Qwen (vs 533-915 s). The Qwen backend transiently returns empty verdicts
  ~7-10% of the time; verdict retry healed all of them in V3 (5/5) where
  sequential runs had silently scored them 0.

Caveats: a flash judge and small samples — directional, not definitive
(V2 vs V3 totals put single-seed noise at roughly ±2 wins). Full reports
(answers + judge reasoning) land in `evals/results/` when you run the
harness.

### SWE suite results (2026-06, ground truth)

The `swe` suite (12 HumanEval-style problems, pass/fail decided by running
unit tests — no judge) was run on three local ollama models. Full mode
(engine on every problem, single-attempt baseline) showed an apparent edge:

| Model | Engine | Baseline (1 attempt) |
|-------|--------|----------------------|
| gpt-oss:20b | 11/12 | 10/12 |
| gemma4:e4b-mlx | 10/12 | 9/12 |

Rescue mode then dismantled that edge. Screening with a **2-attempt**
baseline first and running the engine only on real failures:

| Model | Baseline solved (pass@2) | Left to rescue | Rescued |
|-------|--------------------------|----------------|---------|
| gpt-oss:20b | 12/12 | 0 | — |
| gemma4:26b-mlx | 12/12 | 0 | — |
| gemma4:e4b-mlx | 11/12 | 1 (max-fill) | **0** |

The honest reading: on problems of this difficulty, the engine's apparent
lift over a single call was mostly **resampling luck** — its ~15 calls give
it many implicit attempts, and simply asking the baseline twice (2 calls)
recovers nearly all of it. The one genuine capability gap (max-fill on the
4B-class model) survived 11 engine calls unrescued. Also observed in full
mode: the engine *regressed* one problem the baseline solved (min-path on
e4b) — synthesis can mangle working code, which is why rescue mode, which
never touches baseline-solved problems, is the default.

Takeaway: for verifiable tasks, compare any scaffold against **pass@k at
matched cost** before crediting the scaffold. The advice-suite results
above face the same critique one level up (their baseline is a single
answer, not best-of-k) — a best-of-2-plus-judge baseline is the next
control to run.

The suite was then extended to 18 problems with the literature's hardest
HumanEval items (`find_zero`, `order_by_points`, `match_parens`,
`decode_cyclic`, …) and rescue mode was run against cloud gemma-4 via the
AI Studio API: **both `gemma-4-31b-it` and `gemma-4-26b-a4b-it` solved
18/18 at pass@2** — the failure set is empty, and even the local 4B-class
`gemma4:e4b` solved 17/18. HumanEval-class problems are saturated for this
model family; demonstrating real engine value on code requires
LiveCodeBench/competition-level difficulty. (Side finding: enforced JSON
mode breaks `gemma-4-26b-a4b-it` — empty/truncated verdicts — hence the
`structured_output=False` fallback to prompt-driven JSON.)

## Pluggable Architecture

The `Coordinator` owns only the search *control flow*. Every decision is
delegated to an injected component, so any stage can be swapped without
touching the engine — the engine is a general-purpose reasoning workflow, and
ToT + GAN is just the default wiring.

| Protocol | Responsibility | Default | Alternatives |
|----------|----------------|---------|--------------|
| `Generator` | expand a node into candidate thoughts | `LlmGenerator` | custom prompts/agent |
| `Evaluator` | score (and optionally refine) a thought | `AdversarialEvaluator` (GAN loop) | `SinglePassEvaluator` (cheap) |
| `Selector` | choose the next search frontier | `BeamSearch(width)` | `GreedySearch` |
| `Synthesizer` | combine thoughts into the answer | `LlmSynthesizer` | custom |

`create_engine(...)` wires the defaults. To customize, build the
components yourself and construct `Coordinator` directly:

```python
from dialectica import (
    Coordinator, BeamSearch, SinglePassEvaluator, LlmSynthesizer,
)
from dialectica.agent import build_default_components

# Start from the defaults, then swap a stage:
generator, _evaluator, _selector, synthesizer = build_default_components()
from dialectica.agent_factory import create_agent
from dialectica.models import DiscriminatorVerdict

discriminator = create_agent(
    role="Discriminator", role_name="Discriminator", output_schema=DiscriminatorVerdict
)

engine = Coordinator(
    problem="...",
    generator=generator,
    evaluator=SinglePassEvaluator(discriminator),   # cheaper: no refinement loop
    selector=BeamSearch(width=5),                    # wider frontier
    synthesizer=synthesizer,
    max_depth=3,
    score_threshold=7.0,
)
result = await engine.run()
```

Any object implementing a protocol's method works (they are
`typing.Protocol`, so no subclassing needed) — e.g. a non-LLM heuristic
`Evaluator`, or a `Selector` that keeps a diverse frontier instead of pure
top-k.

## Key Components

### Coordinator
Orchestrates the three-phase workflow against the stage protocols:
- Initialize → Explore → Synthesize
- Manages the thought tree and active beam
- Delegates generation, scoring, selection, and synthesis to injected components

### AgentFactory
Creates agents from role templates:
- Standardized system prompts
- Tool configuration per role
- Model configuration per role
- Runtime agent instantiation

### AdversarialEvaluator
Implements GAN-style evaluation:
- Generator proposes/refines thoughts
- Discriminator critiques with feedback
- Iterative refinement loop
- Structured evaluation results

### ThoughtData Model
Validates thought structure:
- Required fields (id, parent_id, depth, content)
- Optional evaluation data
- GAN round tracking
- Evaluation history

## Performance Considerations

**Token Consumption:**
- GAN evaluation: 2-6 LLM calls per thought (depending on rounds)
- Beam search: beam_width × max_depth iterations
- Typical problem: 50-200 thoughts, 200-800 LLM calls

**Optimization Strategies:**
- Reduce `max_gan_rounds` to 1-2 for faster execution
- Raise `score_threshold` to prune harder; lower it to explore more paths
- Narrow the beam (`beam_width`) or use `GreedySearch` to cut fan-out
- Use a lighter model for the Generator and a stronger one for the Discriminator
- Swap in `SinglePassEvaluator` to skip the refinement loop entirely

## Troubleshooting

### Import Errors
```bash
# Ensure Python 3.11+
python --version

# Reinstall dependencies
rm -rf .venv
uv sync
```

### ADK Version Mismatch
```bash
# Check installed version
uv pip show google-adk

# Should show 2.1.0 or higher
```

### API Key Issues
```bash
# Test Google AI Studio
export GOOGLE_API_KEY=your-key
uv run python -c "from dialectica import create_engine; print('OK')"
```

## Contributing

Contributions welcome! Areas of interest:
- New stage implementations (`Generator` / `Evaluator` / `Selector` / `Synthesizer`)
- Alternative search/selection policies (e.g. diversity-preserving frontiers)
- Performance optimizations
- Documentation improvements
- Test coverage

## License

[MIT](https://github.com/FradSer/dialectica/blob/main/LICENSE)

## References

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — propose → evaluate → keep-best loop
- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [Tree of Thoughts Paper](https://arxiv.org/abs/2305.10601)

## Acknowledgments

Built with [Google ADK](https://github.com/google/adk-python), inspired by Tree of Thoughts research, [karpathy/autoresearch](https://github.com/karpathy/autoresearch)'s autonomous keep-best loop, and Claude Code's composable workflows.
