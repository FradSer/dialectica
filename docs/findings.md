# Findings and research record

Historical, conditional observations moved out of the README. They describe the tested models, tasks and protocols, not universal laws. The README keeps only the summary and the shipped surface.

[← Back to README](../README.md) · [简体中文](findings.zh-CN.md)

## Headline findings (measured, no preset conclusion)

The numbered findings below are historical observations on the tested tasks,
models and evaluation protocols. Their rankings are not universal laws. Older
judge disagreement was recorded as a tie; the new evidence harness preserves it
as inconclusive. Nominal call matching does not establish token or dollar parity.

1. **Where an engine genuinely wins — capability, not quality.** On tasks that require *acting* (the agentic hidden-oracle benchmark), a small model with `agent(tools=[...])` scored **8/8** vs a single call's **0/8**: it probes the hidden function, infers the rule, and implements it — a single call can't know an arbitrary rule without probing. This is the genuine value class.

2. **Where scaffolds do NOT win — self-contained result quality.** Judged against a *matched-cost* baseline, **the tested pure-LLM scaffolds did not beat the tested single-call controls on self-contained tasks**: the dialectic pattern went **0-3-2** vs a prompt-matched strong baseline at every model size (the earlier 4-1-0 "win" was prompt + length, not structure). The **repair** engine beats a *single* call but exactly **ties matched-cost best-of-K** on pass-rate — its real edge is **cost** (best-of-N reliability at ~1/3 the calls). On *open-ended meta-tasks*, the picture differs — see finding #9 (the dialectic, correctly tuned, beats a prompt-matched single call).

3. **The tree structure is *dominated*, not just unhelpful.** On **Game-of-24** — ToT's *own* canonical benchmark — a faithful ToT scored **14/15 and lost to a single call's 15/15 at ~34× the cost**: modern models one-shot the task the 2023 paper's GPT-4 failed 96% of the time. At matched compute under a blind judge, the ToT+GAN pattern went **0-4-1 / 0-2-3 / 0-1-4** (vs single / best-of-N / self-refine) — it *never won a matchup*. The quality order is **self-refine ≥ best-of-N ≥ single ≥ tree-scaffold**.

4. **The value window is closed across the accessible model range.** ToT only helps where the base model fails alone but search can recover — a "fails-but-fixable" band. Probing the *hardest* Game-of-24 puzzles against **four model tiers** (the weakest cloud models available) a single call scored **5/5 on every model, every puzzle**. There is no accessible weak model that fails these tasks, so there is no gap for search to recover — the boundary has moved past this task.

5. **Heterogeneous ensemble — the scorer's signal is not what does the work (2026-06-26).** The ensemble was designed as a fourth honest win lever — *independence* ranked by a mandatory ground-truth-grade signal. A two-axis honesty gate falsified the signal half of the thesis while surfacing a real, narrower result:
   - **Code (ground-truth verifier, 6 problems, budget 6):** ensemble+signal **6/6**, best-single best-of-6 **6/6**, blind-pick **6/6** — **CUT**: both models one-shot every problem, so heterogeneity and the signal both have empty headroom. Saturation, same shape as finding #4.
   - **Open-ended meta (blind LLM-judge, 5 problems, budget 6, position-swap):** ensemble+signal beat a prompt-matched single call **3-1-2** — *the pattern does improve answer robustness on open-ended tasks* (the code axis couldn't measure this). But the **blind-pick arm** (signal replaced by a constant) also beat single **3-1**: the gain is **attributable to roster heterogeneity, not the scorer's ranking signal**. Per H1's signal-attribution clause: **CUT**.
   - **Takeaway:** a *no-scorer* multi-model best-of-N (sample N heterogeneous models, keep one) captures the robustness gain the ensemble shows on open-ended tasks; the float scorer adds no measurable lift over blind-pick. The repair sub-criterion was also **CUT** (multi-model-repair@6 vs single@6: 6/6 vs 6/6, **0 model-switch rescues**).

6. **Heterogeneous reflection — the honest meta-task lever (2026-07-08).** `reflection_pattern.py` implements the structured gather → frame → critique → synthesize pipeline with per-angle model assignment — no AB-MCTS, no LLM scorer. On the full **5-problem meta set** (blind position-swap judge, cliproxy roster `openai:qwen3.6-flash` + `openai:glm-5.2`, `JUDGE_MODEL_CONFIG=openai:glm-5.2`, `DIALECTICA_DISABLE_THINKING=true`):
   - **`evals/reflection_ablation.py` — hetero vs homo vs single:** heterogeneous reflection beat a prompt-matched single call **5-0-0** and beat the same pipeline on one model **5-0-0** — the gain is **attributable to roster heterogeneity**, not merely multi-stage shape.
   - **`evals/workflow_ablation.py` — homo vs single (control):** the homogeneous reflection pipeline beat single **4-0-1** (NET **+4**) — the pipeline shape *does* help on meta-tasks, but heterogeneity adds the remaining edge (including the one problem where homo tied single but hetero won).
   - **Takeaway:** for open-ended reflection/meta-tasks, use heterogeneous multi-angle reflection; do not resurrect ensemble float-scorer ranking. Reproduce: `uv run python -m evals.reflection_ablation` and `uv run python -m evals.workflow_ablation` (same cliproxy env as finding #5).

7. **Multi-model quality workflow modes — expanded pool (2026-07-09).** `quality_workflow_pattern.py` unifies three hetero compositions on **10 problems** (5 meta + 5 default; blind judge, same cliproxy roster as #6):
   - **vs single:** homo reflection **4-0-6** (NET +4); hetero reflection **10-0-0** (NET +10); hetero adversarial **9-0-1** (NET +9); hetero dialectic **9-0-1** (NET +9).
   - **vs hetero reflection (does the extra stage help?):** adversarial **2-0-8** (NET +2); dialectic **0-1-9** (NET −1).
   - **Takeaway:** hetero `reflection` is the default — it sweeps the expanded pool. Extra adversarial-rival or one-round dialectic stages add no consistent lift over hetero reflection (mostly ties; dialectic loses one head-to-head). Prefer `create_reflection_engine`; keep `quality_workflow_pattern` for mode comparison only. Reproduce: `uv run python -m evals.quality_workflow_ablation`.

8. **Access lists — a context-visibility lever, ported from Sakana Fugu (2026-07-12).** A study of Sakana's Fugu/Fugu-Ultra orchestrators (TRINITY + The Conductor, ICLR 2026) provides a distinct architectural example: Fugu's win over each single worker comes from **model independence + a learned router**, not tools the workers lack, and a learned communication topology with per-step access lists. The mechanism implemented here without training is the **access list** — `agent(sees=[...])` now ships as a kernel primitive: default full isolation, opt-in to inject only designated prior steps' outputs. It is wired into the reflection recipe via `use_access_lists=True` (each critique sees only its own gather angle; synthesize sees the tension + critiques, not the full transcript), and verified against a live model (`glm-5.2` via an OpenAI-compatible endpoint). The measured reflection numbers above used inlined prompts, so access-list mode stays opt-in until an ablation shows it lifts or ties on the same matrices. Reproduce the live check: `uv run pytest -m e2e_access`.

9. **The dialectic, correctly tuned, beats a prompt-matched single call — on open-ended meta-tasks (2026-08-05).** The 0-3-2 result (finding #2) is **not the whole story**: that dialectic was under-tuned. Two pure-LLM, same-model changes — a **sharpened `SYNTHESIS_PROMPT`** (make ONE binding decision, give the precise measurable trigger, name the condition where each side wins, carry forward specific numbers — the same bar the reflection pattern holds its synthesis to) and a **deeper spiral** (`max_rounds` 3 → 5) — flip the dialectic from **−0.500 to +0.600 NET** vs a prompt-matched strong single call, confirmed over **two independent runs** (+0.100, +0.600). Methodology matters: this used a **continuous 0-10 score** (blind judge grades each answer against `DEFAULT_CRITERIA`, NET = mean score diff), not the discrete win/lose/tie NET whose ±4 run-to-run swing made the earlier measurement unreadable. Rejected directions: sharpening the THESIS prompt too (−0.333) and two rivals per round (`perspectives=2`, −0.567) both regressed and were reverted. Caveat: measured on the 3 meta problems, single judge (gpt-5.5), continuous-score design; the same tuning on the full 5-meta pool is not yet measured.

## Research update: historical findings are conditional

As of **2026-10-04**, this research update screened **32 primary-source papers**
and completed **7 real-model studies with 576 generation trials**. The
[literature matrix](research/2026-10-03-literature.md) records dates,
reading depth and local implementation decisions; screening does not mean that
all 32 papers were fully reviewed or replicated. The
[completion audit](research/2026-10-04-completion-audit.md) links requirements
to saved verification, and the
[raw-record integrity audit](research/results/2026-10-04-heldout-v1/final-integrity-audit.json)
reconciles the completed studies. Generation trials are experimental arm runs,
not individual model calls; calibration and judging are metered separately.

The [frozen seven-study campaign](research/2026-10-04-heldout-protocol.md)
is complete. All 576 generation trials, report/protocol/analysis bindings and
record-level usage sums were verified before final dependency changes. The batch
reports **3,631,216 tokens / 3,789 observable model turns**, including calibration
and judging, and retains **30 failed generations**. Unknown usage was zero in
this batch; earlier gateway failures with unknown usage remain separate evidence.
These are reported costs, not provider billing or hidden HTTP request counts.

| Held-out comparison | Observed result | Adoption decision |
|---|---|---|
| [Source-grounded decisions](research/2026-10-04-heldout-evidence-result.md) | Exploratory positive panel signals for self-refinement vs Gemini single and heterogeneous reflection vs Qwen single; no established superiority vs GPT single | Keep reflection as a reference pattern; synthetic quote validity and panel agreement do not prove decision correctness or human alignment |
| [Claims K=6](research/2026-10-04-heldout-claims-k6-result.md) | Claims 6/24; consensus/self-refinement 7/24; single 4/24 | Claims-versus-single interval retains zero; no stable API promotion |
| [Claims K=3](research/2026-10-04-heldout-claims-k3-result.md) | Claims/self-refinement 7/24; single/consensus 3/24 | Claims-versus-single interval retains zero; no stable API promotion |
| [Meta budget 12](research/2026-10-04-heldout-meta-budget12-result.md) | Single 5/24; consensus 3/24; self-refinement 8/24; staged 2/24; direct 3/24 | All differences against single retain zero; controllers remain research modes |
| [Meta budget 6](research/2026-10-04-heldout-meta-budget6-result.md) | Single 5/24; consensus 4/24; self-refinement 10/24; staged 4/24; direct 0/24 | All differences against single retain zero; favorable self-refinement point estimates are insufficient for adoption |
| Strong single controls: [meta](research/2026-10-04-heldout-strong-meta-result.md) / [claims](research/2026-10-04-heldout-strong-claim-result.md) | GPT 24/24 under each output contract | Observed ceilings on this pool, not universal success or tests of mechanisms on GPT |

[Candidate/selection diagnostics](research/2026-10-04-heldout-selection-diagnostics.md)
find no correctness change from claim weighting on the same returned candidates.
Meta controllers have low candidate coverage; self-refinement loses correct
intermediate answers at final selection. Failed claim trials have incomplete
coverage rather than assumed zero. These post-hoc diagnostics guide future
research, not retuning on the frozen held-out pool. Intervals condition on small
task pools and are exploratory without multiplicity correction; token costs are
unequal. The shipped surface remains Workflow and verifier-guided repair.

The findings above describe the tested models, tasks and protocols. They do not
establish a necessary-and-sufficient law that scaffolds can only win by adding
external information. Small task pools, saturation, uneven prompt constraints,
call-count-only cost accounting and a single judge limit generalization.

Recent counterevidence motivated the controlled evaluation:
[claim-level falsification](https://arxiv.org/abs/2608.11994) and
[structured meta-reasoning](https://arxiv.org/abs/2609.38147) report benefits from
reallocating inference computation, while also documenting budget/model limits.
These are authors' results, not local replications. The current research upgrade
tracks hypotheses, sources and acceptance gates in
[the upgrade contract](research/2026-10-03-upgrade.md) and
[literature matrix](research/2026-10-03-literature.md). New superiority claims
require strong prompt-matched controls, complete per-arm cost receipts,
held-out tasks, repetitions and reliable evaluation; E2E proves execution only.

The new [claim-falsification research pattern](../examples/patterns/claim_falsification_pattern.py)
implements independent claim assessment and weighted candidate selection.
[Its comparison harness](../evals/claim_ablation.py) records controller/assessment
costs, raw candidates, coverage and same-candidate unweighted selection. Initial
live development trials found a zero-coverage floor at fourteen-project tasks;
see [pilot diagnostics](research/2026-10-04-pilot-diagnostics.md). This
pattern remains experimental after the repeated held-out comparisons: no
selection benefit or established quality advantage justified promotion.

The [meta-reasoning research pattern](../examples/patterns/meta_reasoning_pattern.py)
implements staged/direct controllers, selective context and stored-artifact
selection; no quality advantage is established. The
[evidence-grounded decision harness](../evals/evidence_ablation.py) separately
meters generation, calibration and judging. Position bias, judge disagreement
and failed calibration remain inconclusive. Its first live pilot passed quote
checks but produced position disagreement, so it has no quality winner. Nominal
allowances count workflow agent steps; underlying retries may issue additional
requests. They do not establish request, token or dollar parity.

The new comparison harnesses save configuration, task text, source/dependency
fingerprints and analysis rules before the first model call, including judge
calibration. Existing experiment paths cannot be reused. For completed
objective-verifier reports, run:

```bash
uv run python -m evals.objective_analysis results.json --output analysis.json
```

Analysis averages repeats within each task and resamples paired tasks. Failed
generation stays in the reliability denominator; unknown usage prevents complete
reported-cost claims. Missing pairs, duplicate trials and inconsistent model task
pools fail analysis. Frozen source/rule drift is rejected by default;
`--exploratory-reanalysis` explicitly records the drift for historical diagnostics.
Intervals are exploratory and unadjusted for multiple comparisons. Degenerate
intervals at a floor or ceiling do not establish certainty or general superiority.

For completed evidence-grounded decision reports, run:

```bash
uv run python -m evals.evidence_analysis evidence.json --output evidence.analysis.json
```

This analysis compares each candidate arm with every declared single-model baseline.
Unresolved preferences retain bounds of [-1, +1] rather than becoming ties. It
reports task-cluster uncertainty and separate generation, calibration and judging
costs. Valid-only preferences are selected-evidence diagnostics; they do not prove
human alignment. Incomplete trial pools or baseline comparisons are rejected.

## Earlier advice-suite matrices (2026-06-10/11) — superseded

The first-round matrices compared the ToT+GAN pattern against a *weaker*
single-call baseline (no matched-prompt control) and an "Innovation"
discriminator criterion that steered toward over-complex answers. They are
superseded by findings #2–#7 above. Recorded here: V1 (Innovation criterion) won technical problems 7-1-1 but lost organizational ones 0-4-2; V2 (Feasibility criterion) pooled to 20-8-2 vs V1's 7-5-3 —
evidence that discriminator criteria steer answer *content*, not just selection,
but neither beats a prompt-matched strong baseline.

## Live verification snapshots

ADK 2.11 live acceptance (2026-10-03): **9 passed, zero skipped, 145.37s** via
cliproxy, using `openai:qwen3.8-flash` for the default/generator/fast model and
`openai:gemini-3.5-flash-lite` for the second reflection model. Coverage includes
access-list visibility, default isolation, all ten heterogeneous reflection
calls, repair, tools + schema with sync workers both disabled and enabled, and
parallel resume with cached context, reported usage and zero-call replay, plus
real-model response failures before event creation (retry success and final
failure both preserve the exact reported token sum). After the final cached-event
accounting fix, both live failure cases were rerun: **2 passed in 21.17s**.
This validates the OpenAI-compatible route; direct Gemini credentials were
invalid, and the available GLM routes were blocked by subscription/routing issues.

Final post-campaign environment verification (2026-10-04): **212 offline passed;
9 real-model E2E passed, zero skipped, 114.77s** with Gemini Flash Lite and GPT-5.5
as the heterogeneous reflection pair. Lint, formatting, package build and dependency
checks are recorded in [the completion audit](research/2026-10-04-completion-audit.md).
The first final live attempt retained 8 passes and one historical-roster routing
failure; the configured available-roster rerun passed every test without changing
assertions. One upstream Pydantic `ReadOnly` warning remains; no unhandled asynchronous
task failure was observed in the passing run. These checks establish execution,
including pre-event failure usage retention, not quality superiority.
