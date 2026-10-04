# Completed held-out meta study: Gemini budget 6

The seventh frozen study completed normally with 120 trials (8 tasks × 3
repeats × 5 arms). All seven terminal report/protocol/analysis hashes,
configuration/task bindings and record-level usage sums were verified before
final environment changes. The batch audit is saved in
`results/2026-10-04-heldout-v1/complete-receipt-audit.json`.

| Arm | Correct / 24 | Reported tokens | Observable turns |
|---|---:|---:|---:|
| single | 5 | 9,466 | 24 |
| consensus | 4 | 55,376 | 144 |
| self_refine | 10 | 120,035 | 144 |
| staged | 4 | 112,224 | 125 |
| direct | 0 | 42,935 | 48 |

Staged passes 4/24, direct 0/24 and single 5/24. Their paired differences are
-0.0417 (interval [-0.25, 0.125]) and -0.2083 (interval [-0.4583, 0]).
Self-refinement passes 10/24, difference +0.2083 (interval [-0.0417, 0.5]);
consensus passes 4/24, difference -0.0417 (interval [-0.125, 0]). All intervals
retain zero. The observed direct-controller floor does not prove universal
failure; bootstrap intervals condition on this eight-task pool.

Reported cost is 340,036 tokens / 485 observable turns, with no generation
failures or unknown calls. Combined with budget 12, controllers show no
established quality advantage over single. Self-refinement is the best observed
point estimate here, but its gain remains uncertain and is not an adoption proof.
Budgets count workflow steps; actual tokens/USD are not matched, and hidden
provider retries/billing remain opaque. Neither study implements a learned
controller or replicates the referenced paper's full benchmark.

The full seven-study batch reports 3,631,216 tokens / 3,789 observable turns,
including calibration and judging. It preserves 30 failed generations across
evidence/claim studies and zero unknown calls in this batch. Earlier gateway
failure pilots with unknown usage remain separate evidence. Strong single
controls are observed ceilings; panel signals are exploratory, not human
alignment proofs. No claim/controller pattern is promoted to stable API.

Final compatible dependency upgrades, coherent documentation and final live
E2E remain required; completion of the experiments alone is not completion of
the whole research upgrade.

Artifacts: `results/2026-10-04-heldout-v1/meta-gemini-budget6.json`,
`meta-gemini-budget6.protocol.json`, `meta-gemini-budget6.analysis.json` and
`meta-gemini-budget6.terminal.json` in that directory.

## Subsequent completion

All seven studies subsequently completed. Earlier pending/running statements
above describe the checkpoint when this study finished. See
[the completion audit](2026-10-04-completion-audit.md) for final environment
verification and [selection diagnostics](2026-10-04-heldout-selection-diagnostics.md)
for candidate coverage and same-candidate comparisons. The frozen raw artifacts
and declared analyses remain unchanged.
