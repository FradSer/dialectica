# Completed held-out claim study: Gemini K=6

Second of seven frozen studies completed: 8 held-out portfolio tasks × 3
repeats × 4 arms = 96 trials. Terminal report/protocol/analysis byte hashes
were verified; task/configuration bindings agree and frozen sources/dependencies
remain unchanged. Failed generation counts as an incorrect system outcome.

| Arm | Correct / 24 | Failed generations | Reported tokens | Observable turns |
|---|---:|---:|---:|---:|
| single | 4 | 8 | 16,704 | 24 |
| consensus | 7 | 4 | 167,556 | 261 |
| self_refine | 7 | 5 | 187,454 | 241 |
| claims | 6 | 2 | 174,198 | 273 |

Consensus and self-refinement each improve success by 0.125 versus single,
with exploratory paired task-bootstrap intervals [0.0417, 0.25]. Claims improve
by 0.0833 with interval [0, 0.2083], which retains zero. Claims are not established
as superior to repeated-call controls; the formal bound analysis uses single as
its baseline and does not provide a direct claims-versus-control interval.

The claim mechanism does not justify API promotion from this result. Its
reported generation cost is about 10.4 times single-call cost. Calls budgets
are workflow-step allowances, not matched token/USD budgets. Failures truncate
some arms before the allowance, so realized turn counts differ. There are
19 generation failures across all arms, with zero unknown calls. Reported total
cost is 545,912 tokens / 799 observable turns, including failures. No hidden
provider request count or billing total is inferred.

Intervals condition on eight observed tasks, average repeats within each task,
and have no multiplicity correction. This is a reduced training-free mechanism
study, not replication of a paper's learned policy or benchmark. K=3 and strong
single-call controls remain pending, as do the other campaign studies and final
runtime verification. Do not select only successful outputs.

Artifacts: `results/2026-10-04-heldout-v1/claims-gemini-k6.json`,
`claims-gemini-k6.protocol.json`, `claims-gemini-k6.analysis.json` and
`claims-gemini-k6.terminal.json` in that same directory.

## Subsequent completion

All seven studies subsequently completed. Earlier pending/running statements
above describe the checkpoint when this study finished. See
[the completion audit](2026-10-04-completion-audit.md) for final environment
verification and [selection diagnostics](2026-10-04-heldout-selection-diagnostics.md)
for candidate coverage and same-candidate comparisons. The frozen raw artifacts
and declared analyses remain unchanged.
