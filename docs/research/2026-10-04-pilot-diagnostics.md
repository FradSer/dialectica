# Development diagnostics, 2026-10-04

This is a development report, not a held-out comparison or superiority claim.
Real calls used the configured cliproxy endpoint. Credentials are not stored.
The oracle exhaustively searches the project subsets and is used only after
the arm has selected its answer. No model-generated code is executed.

## Initial headroom pilot

Raw artifact: [portfolio pilot](results/2026-10-04-portfolio-pilot.json).
Eight seeded development tasks, fourteen projects each, one call per model/task.

| Model | Strict JSON success | Content success allowing a whole-answer fence | Reported tokens |
| --- | --- | --- | --- |
| `openai:qwen3.8-flash` | 0/8 | 0/8 | 24,717 |
| `openai:gemini-3.5-flash-lite` | 0/8 | 0/8 | 3,256 |

Qwen: two unparseable answers, three mutual-exclusion failures, two capacity
failures, one feasible but suboptimal result. Gemini: three exclusion failures
and five capacity failures after fence normalization. Strict JSON-only parsing
had also counted several fenced answers as format failures. The diagnostic
normalization strips only an entire enclosing fence; it does not extract a
preferred answer from prose or repair task content. Original outputs remain
unchanged in the artifact.

Some Qwen requests produced very long reasoning despite the requested thinking
disable flag. This demonstrates why actual usage must be reported rather than
assuming equal requests or configuration imply equal compute.

## Structured comparative pilot

Raw artifact: [claim comparison](results/2026-10-04-claim-dev-pilot.json).
Two development tasks at size fourteen, `openai:gemini-3.5-flash-lite`, one
trial per arm. Every generation arm uses the same answer-plus-five-claims
schema and task statement. Single uses one workflow agent step; consensus and
self-refine use four; CLR uses two generations plus two assessments. All costs
are recorded per arm. These are matched workflow-step allowances among the
multi-call arms, not matched provider requests, tokens or dollars; underlying
SDK/provider retries remain opaque.

| Arm | Correct selected answers | Candidate coverage | Reported tokens across two tasks |
| --- | --- | --- | --- |
| Single | 0/2 | 0/2 | 1,668 |
| Consensus | 0/2 | 0/2 | 5,861 |
| Self-refine | 0/2 | 0/2 | 7,500 |
| CLR | 0/2 | 0/2 | 5,432 |

There was no correct CLR candidate to recover. Consequently this pilot cannot
test the proposed selection advantage. The next development pilot reduces
size to eight before any held-out protocol is frozen. No held-out outcome has
been inspected or used for tuning. Only two tasks and one trial were compared;
the fixed arm order is another limitation. Wider evaluation must randomize or
counterbalance order and use repeated trials and uncertainty estimates.

CLR's inference equations and independent claim-only assessment are implemented
from [the primary paper](https://arxiv.org/html/2608.11994v1). The local models,
task family, sample count and structured decoding differ from the authors'
benchmark setup. This is a mechanism experiment, not a reproduction of their
reported scores. LLM claim survival is a heuristic; it is not ground truth.

## Size-eight development check

Raw artifact: [size-eight comparison](results/2026-10-04-claim-dev-size8.json).
Same four arms and model, two independently generated size-eight development
tasks, one trial. All arms succeed on the first task and fail on the second.
All have coverage on the first and zero coverage on the second. CLR's weighted
selection also matches unweighted selection on its own candidates in both cases.

| Arm | Correct selected answers | Reported tokens across two tasks |
| --- | --- | --- |
| Single | 1/2 | 1,149 |
| Consensus | 1/2 | 4,471 |
| Self-refine | 1/2 | 5,356 |
| CLR | 1/2 | 4,593 |

The current sample has both successful and unsuccessful tasks, but it still
does not exercise recovery of a correct minority candidate. No benefit is
established. More development tasks and model assignments are required before
freezing a held-out protocol; two trials cannot justify statistical or general
quality claims. No API promotion follows from this check.

## State-transition development pilot

The [24-operation state pilot](results/2026-10-04-meta-state-dev24.json)
completed four development tasks and five arms with Gemini Flash Lite. All
20 selected answers failed the deterministic interpreter; all candidate
coverage was zero. Reported tokens were 2,433 single, 14,608 consensus,
15,904 self-refine, 20,795 staged and 5,814 direct. This floor effect prevents
a useful quality comparison. A shorter development headroom pilot follows;
no held-out data has been inspected.

Staged/direct execution at portfolio size eight also completed in a
[one-task live smoke](results/2026-10-04-meta-dev-smoke-v2.json), with both
answers passing the objective oracle. It verifies execution, not superiority.

## Permanent provider rejection and unknown usage

GLM's generic alias was rejected for an absent provider routing header. Its
provider-qualified route then returned expired-plan billing text under 429.
Model catalog presence therefore did not establish usability. No account or
subscription configuration was changed. The original expiry probe was
interrupted after repeated identical permanent failures; it is not a completed
quality trial.

The [fixed-runtime live receipt](results/2026-10-04-expired-plan-failfast.json)
records one failed call, one unknown-usage attempt, no raw model output and
16.74 seconds. The gateway response was a cooldown error retaining the upstream
expired-plan cause. That permanent cause now bypasses the rate-limit retry
loop. Zero *reported* tokens here does not mean zero cost.

Nominal workflow call allowances count agent steps; SDK retries or tool turns
can issue additional provider requests. New reports label this unit explicitly.
Equal steps do not establish request, token or dollar parity.

## Evidence-grounded decision execution pilot

The [one-task decision smoke](results/2026-10-04-evidence-dev-smoke.json)
used Gemini Flash Lite for single/self-refine generation and Gemini/Qwen Flash
as separately metered, position-swapped judges. Both judges identified the
deliberately infeasible fabricated calibration answer. This calibrates one
obvious error, not general judge accuracy. Both generated answers passed quote
identity/structure checks, which do not prove their inference validity.

Gemini preferred the single answer in both positions; Qwen changed its judgment
after position swapping. The aggregate result is inconclusive with no winner.
All generation, calibration and comparison receipts retain prompts, raw outputs
and usage. This demonstrates the incomplete-measurement path rather than a
self-refinement quality benefit. No held-out trial or statistical conclusion
follows from this one development task.

The completed v1 smoke used 11 runtime calls and 10,203 reported tokens:
2,067 calibration, 2,486 generation and 5,650 comparison. Every aggregate
reconciles with its raw call records; unknown-usage attempts were zero.
Independent review subsequently identified that v1 could record a quality win
for ungrounded answers or duplicate runtime judge families under different
declared aliases. Protocol v2 closes both gates and saves the source-card map.
Historical v1 artifacts remain unchanged, with that limitation attached.

The [v2 live rerun](results/2026-10-04-evidence-dev-smoke-v2.json) completed
with both quote gates passing and runtime model families matching Gemini/Qwen.
Position disagreement again prevented a quality winner. Independent re-review
confirmed both v2 validity repairs and 20 focused tests. The current baseline
uses the first roster model only; this smoke cannot distinguish model choice
from orchestration. Multi-model comparisons require single baselines for each
roster member before the held-out protocol is frozen.

## Neutral-template and roster controls

The [old/neutral template comparison](results/2026-10-04-generator-prompt-dev-ablation.json)
randomized the two prompt conditions within each model/task pair on four
development state tasks (eight operations) and two models. Both conditions
scored 0/4 on both models. Old/neutral reported totals were 1,585/1,492 tokens
for Gemini and 4,201/4,278 for Qwen. The neutral template removes an inherited
ToT role conflict; this floor-effect experiment does not show better accuracy.
Raw answers include both incorrect states and failures to return the required
JSON, so formatting and reasoning failures must be distinguished in subsequent
development. No hidden state was supplied to a model.

The [v3 roster-control smoke](results/2026-10-04-evidence-roster-dev-smoke-v3.json)
adds a separate one-call Qwen baseline to the Gemini baseline. It completed
16 runtime calls and 17,021 reported tokens with zero unknown reports;
aggregate totals reconcile with raw call records. Self-refine used two calls
and the mixed roster. Both judges preferred it against Gemini's single answer,
but both displayed position disagreement against Qwen's single answer. The
second comparison is inconclusive; the first is one development observation
at greater generation cost, not an orchestration or held-out superiority claim.
Each judge receipt identifies its baseline arm, preventing cross-baseline cost
or verdict aggregation. A fresh reviewer verified the complete 178-test suite.

[Real callback-failure E2E](results/2026-10-04-neutral-failure-metering-e2e.txt)
passed both recovery and terminal-failure cases after the shared-template
change. The tests intentionally fail after actual model usage is received but
before ADK event creation; all response usage survives in exception/retry,
budget and journal totals. This is execution/metering evidence.

## Independent review and measurement changes (earlier)

The initial artifacts above store aggregate arm costs and parsed candidate
outputs. They do not contain raw transport responses or full input receipts;
they remain saved unchanged as development diagnostics. The observer has since
been extended to save each runtime call's prompt, static system instruction,
model name, stage label, raw response, usage, duration and failure type. Stage
labels separate generation from assessment overhead. No provider configuration
objects or credentials are serialized. New runs will carry these records.

Real-model receipt E2E: [saved raw call records](results/2026-10-04-claim-receipts-smoke.json)
contain four calls (two generation, two assessment), 2,247 reported tokens,
nonempty actual prompts and raw responses, and per-call durations. Aggregate
token usage equals the sum of the four call records. The selected answer passed
the size-eight oracle. This validates recording and execution; it adds no
comparative superiority evidence.

The research implementation also differs from CLR's benchmark protocol: its
structured generation does not request a separate full reasoning-trace field;
the fixed claim-generation prompt is shared by all local controls. The saved
v1 pilots retained malformed answer strings; protocol v2 now supplies a
task-specific syntactic prediction parser and omits unparseable predictions
from both weighted and unweighted selection. No parsed candidate produces an
explicit failure, not a synthetic answer. Claims are instructed not to restate
answers, but this semantic condition is not structurally guaranteed. These
limitations must be addressed or explicitly controlled before any replication
claim. The current experiments support none.
