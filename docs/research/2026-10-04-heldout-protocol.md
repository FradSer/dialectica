# Repeated held-out campaign: protocol before dispatch

Status: declared before the first campaign model call. This is a local
predeclaration, not external preregistration. Development observations informed
the difficulty and budgets; held-out outcomes must not inform changes to this run.

## Question and scope

Does claim-level falsification or structured artifact orchestration improve
objective correctness relative to prompt-matched single calls, consensus and
self-refinement at declared workflow-step allowances? On source-grounded decisions,
does additional orchestration improve panel preference relative to each roster
model's single-call baseline? Actual token and latency differences remain part
of the comparison; nominal allowances do not establish equal compute or billing.

## Frozen studies

All objective studies use eight held-out portfolio tasks of size eight, generated
from the held-out seed 71004. Each task is repeated three times. The objective
oracle stays in the evaluator and is never feedback to a generator or controller.

| Study | Model | Arms | Allowance |
|---|---|---|---|
| meta-gemini-budget6 | openai:gemini-3.5-flash-lite | single, consensus, self_refine, staged, direct | 6 workflow steps |
| meta-gemini-budget12 | openai:gemini-3.5-flash-lite | same five arms | 12 workflow steps |
| claims-gemini-k3 | openai:gemini-3.5-flash-lite | single, consensus, self_refine, claims | 6 steps; claims uses 3 generation + 3 assessment |
| claims-gemini-k6 | openai:gemini-3.5-flash-lite | same four arms | 12 steps; claims uses 6 generation + 6 assessment |
| strong-meta-single | openai:gpt-5.5 | single, matching meta output contract | 1 step |
| strong-claim-single | openai:gpt-5.5 | single, matching claim output contract | 1 step |
| evidence-roster-budget12 | Gemini above, openai:qwen3.8-flash, openai:gpt-5.5 | single per roster model, self_refine, reflection_homo, reflection_hetero, staged, direct | 12 generation steps for multi-step arms |

Evidence uses six held-out source-grounded decisions, seed 101004, each repeated
twice. Judges are the declared Gemini and Qwen models; calibration and position-
swapped judging are measured separately. Their family overlap with generators is
a potential preference bias; calibration tests obvious factual violations and does
not validate general judgment accuracy. This is synthetic evidence, not real-world
decision acceptance or human validation.

Strong-model objective studies are single-call controls only. They cannot establish
that either new mechanism works on the strong model. Meta and claim results remain
separate because their answer/claim contracts differ.

Arm order seeds: meta 10430, claim 10431, evidence 10427. Study order seed 10432
gives evidence-roster-budget12, claims-gemini-k6, claims-gemini-k3,
strong-meta-single, strong-claim-single, meta-gemini-budget12,
meta-gemini-budget6. Every study and the source archive are frozen before this order
begins; randomization does not remove temporal provider drift.

## Analysis and validity

Objective analysis averages repetitions within each task, then performs paired
task-cluster bootstrap: 2,000 draws, seed 10429, exploratory 95% interval. Generation
failures remain incorrect system outcomes in the denominator. Candidate coverage
and same-candidate selection diagnose generation versus selection separately.

Evidence analysis uses bounded task-level preferences: valid candidate/baseline/tie
is +1/-1/0; inconclusive measurements retain [-1,+1]. It reports identification
bounds and an outer bootstrap interval, 2,000 draws, seed 10433. Valid-only means
are selected-evidence diagnostics. Unknown outcomes are never silently converted
into ties. Both answers must pass grounding, and recorded distinct recognized judge
families must match the declaration and agree across positions.

Intervals are exploratory, unadjusted for multiple comparisons and conditional on
this small task pool. Degenerate intervals do not prove certainty. No method is
promoted solely on a point estimate, a subset of valid panel outcomes, or E2E success.
Quality, coverage, costs, uncertainty and stronger controls must be considered together;
unsupported variants remain examples rather than shipped engines.

## Execution and evidence preservation

The campaign saves source bytes and dependency manifests in sources.zip; parent
and child protocols bind configuration, complete task pools, source hashes and
dependencies. Analysis is bound to the exact raw report and protocol bytes. Checks
before/after each study reject source or archive drift. Each study has a separate
terminal receipt for completion, failure or cancellation. Existing paths cannot be
overwritten; harness failures stop the campaign with the original outcomes preserved.

Runtime receipts include raw prompts/outputs, reported tokens, missing usage,
observable ADK model turns and latency. No credentials are saved. Failed calls before
events count as observed attempts; missing token metadata is unknown, not zero cost.
Opaque SDK/provider retries and billing remain unmeasured; no token, dollar or HTTP
request parity is asserted. Shell cliproxy configuration supplies credentials;
Qwen thinking is disabled, workflow concurrency is four.

No automatic restart, hidden final synthesis, oracle-assisted repair, retrospective
protocol edits or held-out tuning is allowed. Measurement defects require explicit
diagnosis and a separately identified future experiment; they do not justify erasing
or silently relabeling this run.
