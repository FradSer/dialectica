# Literature screening, 2026-10-03

Reading labels: **methods inspected** means relevant full-text method/limitations sections were inspected; **abstract inspected** means bibliographic/abstract screening, not full replication. Reported improvements below belong to the authors; none is yet a Dialectica result. Dates refer to source submission/revision, not search crawl dates.

| Primary source | Date / depth | Mechanism or relevance | Local decision |
| --- | --- | --- | --- |
| [Thinking Before Thinking](https://arxiv.org/abs/2609.38147) | 2026-09-29; methods inspected | Structured control over persistent artifacts; overhead charged with workers; gains depend on budgets and models. | Implement a budget-accounted controller and direct-controller ablation; do not claim full reproduction of ProgramBench. |
| [Control-Data Flow Separation](https://arxiv.org/abs/2609.00621) | 2026-09; methods inspected | Typed execution protocols separate from optimizable natural-language task content. | Enforce action targets, artifact references and termination in Python. |
| [Claim-Level Reliability Assessment](https://arxiv.org/abs/2608.11994) | 2026-08-12; methods inspected | Independent claim refutation; reliability aggregation; comparisons allocate verification as part of the sampling budget. | Implement a falsification ablation; objective validators remain independent of LLM assertions. |
| [Semantic Uncertainty-Guided Orchestration](https://arxiv.org/abs/2608.14707) | 2026-08-11; abstract inspected | Semantic agreement guides verification, re-prompting and reassignment. | Candidate adaptive policy; measure sampling overhead before adoption. |
| [Learning Simple Test-Time Environments](https://arxiv.org/abs/2608.29305) | 2026-08-29; abstract inspected | Environment decomposition and test-time adaptation. | Evidence for difficult tool environments; do not substitute toy tasks for its web-agent claims. |
| [Latency-Aware Orchestration](https://arxiv.org/abs/2609.03335) | 2026-09; abstract inspected | Scheduling heterogeneous serving resources and workflow dependencies. | Report wall-clock latency; hosted GPU scheduling is outside this library's initial implementation. |
| [Sakana Fugu Technical Report](https://arxiv.org/abs/2606.21228) | 2026-06-19; abstract inspected | Trained query-adaptive heterogeneous orchestration; quality/latency variants. | Supports selective contexts and heterogeneous dispatch; trained policy gains cannot be attributed to an untrained clone. |
| [Learning to Orchestrate with the Conductor](https://arxiv.org/abs/2512.04388) | 2025-12; ICLR 2026; abstract inspected | Learned natural-language communication topology and targeted assignments. | Inspiration for typed plans and context selection; training is a distinct requirement. |
| [FutureWeaver](https://arxiv.org/abs/2512.11213) | revised 2026-06-01; abstract inspected | Reusable collaboration modules; short/long-horizon budget planning. | Compare reusable actions with direct control under the same allowance. |
| [Multi-Agent Reasoning Improves Compute Efficiency](https://arxiv.org/abs/2605.01566) | 2026-05-02; abstract inspected | Pareto analysis across methods and model sizes; equal-compute comparisons can favor debate/MoA. | Replace universal negative assertions with conditional, measured claims. |
| [Team of Thoughts](https://arxiv.org/abs/2602.16485) | 2026-02-18; abstract inspected | Heterogeneous tool-agent orchestration and calibration. | Compare heterogeneous and homogeneous assignments separately. |
| [MAS-Orchestra](https://arxiv.org/abs/2601.14652) | 2026-01-21; abstract inspected | Controlled task dimensions: depth, horizon, breadth, parallelism, robustness. | Build evaluation families varying these dimensions rather than only easy puzzles. |
| [MAS-ProVe](https://arxiv.org/abs/2602.03053) | 2026-02; abstract inspected | Process verification effectiveness and limitations in agent systems. | Include verifier failures, selection gaps and corrected-to-wrong transitions. |
| [Preventing Error Propagation](https://arxiv.org/abs/2606.29026) | 2026-06-27; abstract inspected | Independent answers followed by communication can both correct and corrupt decisions. | Keep independence controls and measure harmful revisions. |
| [AgentCollab](https://arxiv.org/abs/2603.26034) | 2026-03; abstract inspected | Self-evaluation-driven collaboration efficiency. | Compare adaptive escalation against fixed fan-out; confidence is not ground truth. |
| [Verifiable Process Rewards](https://arxiv.org/abs/2605.10325) | 2026-05-11; abstract inspected | Dense oracle-grounded supervision; relies on reliable intermediate verification and training. | Use intermediate executable checks where available; do not label inference-only code as RL replication. |
| [Judging the Judges](https://arxiv.org/abs/2604.23178) | 2026-04-25; abstract inspected | Style and model-dependent judge bias persist beyond position swaps. | Multiple judge families, constrained output format and calibration controls. |
| [Bias and Uncertainty in Judge Estimation](https://arxiv.org/abs/2605.06939) | 2026-05-07; abstract inspected | Calibration instability can reverse apparently confident comparisons. | Report uncertainty and judge disagreement; no single-judge universal claims. |
| [Mitigating Scoring Bias](https://arxiv.org/abs/2608.05726) | 2026-08-06; abstract screened | Numerical scoring biases vary with judge, task and score range. | Avoid treating arbitrary scalar scores as calibrated probability. |
| [Chain-of-Verification](https://arxiv.org/abs/2309.11495) | 2023-09-20; abstract inspected | Independently verify questions before revising an answer. | Older control for whether claim targeting beats generic self-refinement. |

## Search coverage and exclusions

### Follow-up screening, 2026-10-04

These nine additional primary abstracts bring the matrix to 29 sources. Full
methods have not yet been inspected for these additions. October-ID searches
did not yield a usable match in this pass; that is not evidence that no newer
papers exist.

| Primary source | Submission / revision | Relevance and local decision |
| --- | --- | --- |
| [Candidate supply and answer selection](https://arxiv.org/abs/2608.25937) | 2026-08-26 / 08-30 | Fixed candidate pools isolate recognition and selection from generation. Record coverage and replay unweighted selection on CLR's own candidates. |
| [Consilience](https://arxiv.org/abs/2608.09898) | 2026-08-10 | Confidence trajectories can favor confidently wrong answers. Do not replace independent validation with confidence alone. |
| [LLM-as-a-Verifier](https://arxiv.org/abs/2607.05391) | 2026-07-06 / 07-07 | Fine-grained verification uses scoring-token logit distributions. A text-only scalar judge would not reproduce this mechanism. |
| [How Inference Compute Shapes Frontier LLM Evaluation](https://arxiv.org/abs/2606.17930) | 2026-06-16 / 07-16 | Outcomes vary with budget, feedback and allocation. Compare cost curves and preserve the information-access contract. |
| [When Is a Multi-Agent Code Judge Actually Grounded?](https://arxiv.org/abs/2609.30328) | 2026-09-23 | Evidence must discriminate between candidates; abstention can identify unsupported comparisons. Inconclusive is distinct from a quality tie. |
| [AgentJudgeBench](https://arxiv.org/abs/2608.26623) | 2026-08-27 | Dependency-workflow judge alignment depends on difficulty and generator/judge pairing. Structured rubrics are not universal calibration. |
| [Cheap Verifiers, Large Blind Spots](https://arxiv.org/abs/2609.01345) | 2026-09-01 / 09-04 | Cascade metrics computed through their own verifier can hide degradation. Use an independent oracle for measured quality. |
| [Single-Agent LLMs under Equal Thinking Token Budgets](https://arxiv.org/abs/2604.02460) | 2026-04-02 / 04-11 | Multi-hop comparisons reveal compute/context confounds and API budget artifacts. Request parity must not be advertised as token parity. |
| [Locating Hidden Failures](https://arxiv.org/abs/2609.17930) | 2026-09-15 | Trace-level failure localization complements final outcomes. Scout is a trained verifier; generic prompting is not its replication. |

Searches covered recent multi-agent reasoning, test-time compute, learned orchestration, claim verification, semantic uncertainty, runtime error propagation, judge bias, and benchmark methodology. Month-specific searches alone returned poor matches; broader recency queries located August/September work, then arXiv pages verified identities and dates. Secondary summaries, Reddit discussions and promotional claims are discovery aids only, not experimental evidence. Infrastructure-only, training-heavy and domain-specific methods must be identified as such instead of silently approximated.

## Working hypotheses

### Judge-focused follow-up, 2026-10-04

Three more primary abstracts bring screening to 32 sources, including a
2026-09-30 submission. Their arXiv abstracts and dates were verified directly;
the entries below do not claim full-method review or local replication.

| Primary source | Submission / depth | Relevance and local decision |
| --- | --- | --- |
| [JuryFlow](https://arxiv.org/abs/2609.40103) | 2026-09-30; abstract inspected | Targets claim-level disagreement instead of forcing panel consensus; its reported benchmark uses automatic entropy-based focal selection rather than a human study. Preserve disagreement diagnostics; do not claim a prompted panel reproduces graph propagation or learned rubrics. |
| [Beyond Consensus](https://arxiv.org/abs/2608.30373) | 2026-08-31; abstract inspected | In the authors' subjective-scoring experiments, asymmetric strict/lenient roles can reduce human alignment. Use the same rubric independently for both local judge families; agreement alone does not prove validity. |
| [JudgeProfile](https://arxiv.org/abs/2609.36705) | 2026-09-29; abstract inspected | Separates perceived response attributes from the weights judges assign to them. Its adaptation uses reference labels. Our obvious-error calibration does not estimate these weights or establish calibrated decision quality. |

These findings motivate uncertainty reporting rather than another unvalidated
judge-debate layer. Multi-model single-call controls also remain necessary:
additional model access must not be credited solely to orchestration.

### Current hypotheses

1. Fixed ten-step reflection can waste compute on easy tasks; budget-aware dispatch may help difficult tasks but can lose at small budgets.
2. Claim-level falsification may improve selection when candidates differ in decisive errors; it can also propagate false refutations. Evaluate both transitions.
3. Roster diversity and control quality must be ablated separately.
4. Equal model-call counts do not imply equal token or dollar budgets. Any incomplete usage marks cost comparisons as incomplete.
5. Existing small-pool wins and saturation losses are useful observations, not a proof of necessary-and-sufficient conditions for scaffold gains.

### Full-text judge follow-up during the frozen campaign

On 2026-10-04, relevant method and limitation sections of three previously
abstract-screened sources were inspected. This increases reading depth, not the
source count. These notes do not change the running campaign's rubric, task pool,
selection rules or hypotheses.

- [JuryFlow, sections 3–4 and 7](https://arxiv.org/html/2609.40103v1):
  claim-verdict entropy selects disputed claims; tag/embedding similarity connects
  them for re-evaluation and subsequent rubric updates. Pairwise scoring runs each
  answer independently and resolves score ties with the development-selected
  strongest judge. All benchmark results use automatic focal selection; human
  benefit remains unvalidated. Reported cost tables count re-evaluation calls,
  rather than the complete initial panel and embedding cost. Correlated consensus
  errors, rubric drift and untested language/domain transfer remain limitations.
  Local implication: preserve frozen independent judgments and full receipts;
  do not add adaptive rubric updates to this campaign or call panel agreement
  evidence of human acceptance. This implication is ours, not a local replication.
- [JudgeProfile, sections 4.2–4.5 and 6.1](https://arxiv.org/html/2609.36705v1):
  linear logistic weights describe how attribute judgments predict overall
  preferences; adaptation fits weights to external reference labels with a
  training/test separation. Agreement on observed attributes does not guarantee
  agreement on the preferred answer. A fixed linear weight vector cannot capture
  all context-dependent trade-offs. Local implication: the current obvious-error
  calibration does not estimate preference weights, establish alignment with users,
  or reproduce this label-dependent adaptation. An unlabeled prompted judge panel
  cannot substitute for the paper's reference-supervised evaluation.
- [Grounded code judging, full short paper](https://arxiv.org/html/2609.30328v1):
  candidate-independent evidence also needs discriminating information. Its
  no-label gate examines repeated proposer questions; withholding unsupported
  comparisons improves accuracy on the retained subset but still trails direct
  judging. Local implication: abstention changes coverage and must stay visible
  in the all-task denominator. The local quote validator authenticates quotations,
  not whether they discriminate between decisions; it is not this paper's gate.

These distinctions constrain later adoption claims; they are not grounds for
changing a held-out protocol after dispatch.
