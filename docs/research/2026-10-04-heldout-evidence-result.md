# First completed held-out study: evidence-roster-budget12

The first of seven frozen studies completed. The terminal receipt binds the
raw report, protocol and analysis byte hashes; task/configuration bindings agree,
and frozen sources/dependencies/archive verify unchanged. Generation covers
96 trials (8 arms × 6 synthetic tasks × 2 repeats); all 60 nonbaseline trials
have comparisons against all three single-call baselines. This is not completion
of the seven-study campaign.

## Reported cost

Generation: 676,254 tokens / 513 observable model turns, including one controller
failure. Judging: 1,118,872 tokens / 708 turns. Calibration: 1,896 tokens / 4 turns.
Total: 1,797,022 tokens / 1,225 turns; zero unknown calls in completed receipts.
These are reported tokens and observable turns, not provider billing or hidden
HTTP requests. The panel costs exceed the generation costs.

| Arm | Trials | Generation tokens | Observable turns | Failed trials |
|---|---:|---:|---:|---:|
| direct | 12 | 21,247 | 24 | 0 |
| reflection_hetero | 12 | 194,272 | 120 | 0 |
| staged | 12 | 52,080 | 69 | 1 |
| reflection_homo | 12 | 152,015 | 120 | 0 |
| single_2 | 12 | 18,304 | 12 | 0 |
| self_refine | 12 | 220,124 | 144 | 0 |
| single | 12 | 8,520 | 12 | 0 |
| single_1 | 12 | 9,692 | 12 | 0 |

## Bounded interpretation

Self-refinement versus Gemini single has 9/12 valid comparisons, identification
bounds [0.5, 1.0] and task-bootstrap outer interval [0.167, 1.0]. Heterogeneous
reflection versus Qwen single has 11/12 valid comparisons, identification bounds
[0.833, 1.0] and outer interval [0.5, 1.0]. These are exploratory panel signals,
conditional on six observed synthetic tasks, without multiplicity correction or
human alignment evidence. Generator/judge family overlap can bias preferences.

Neither establishes superiority over GPT single: each has only 2/12 valid
comparisons against GPT, with outer intervals [-1.0, 1.0]. Most other contrasts
also retain zero in their outer intervals. Do not select only valid judgments
or convert unresolved outcomes into ties. The staged controller's contract
violation remains a failed generation outcome with its full cost retained.

New patterns remain research examples. No stable API promotion or default
change follows from this first study alone. Remaining objective studies and
final environment verification are still required.

Artifacts: `results/2026-10-04-heldout-v1/evidence-roster-budget12.json`,
`evidence-roster-budget12.protocol.json`, `evidence-roster-budget12.analysis.json`
and `evidence-roster-budget12.terminal.json` in that same directory.

## Subsequent completion

All seven studies subsequently completed. Earlier pending/running statements
above describe the checkpoint when this study finished. See
[the completion audit](2026-10-04-completion-audit.md) for final environment
verification and [selection diagnostics](2026-10-04-heldout-selection-diagnostics.md)
for candidate coverage and same-candidate comparisons. The frozen raw artifacts
and declared analyses remain unchanged.
