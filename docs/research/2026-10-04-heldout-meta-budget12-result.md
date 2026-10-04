# Completed held-out meta study: Gemini budget 12

Sixth of seven frozen studies completed: 8 held-out portfolio tasks × 3 repeats
× 5 arms = 120 trials. Terminal report/protocol/analysis byte hashes and
configuration/task bindings were verified, as were all record-level usage sums
and the unchanged frozen sources/dependencies/archive.

| Arm | Correct / 24 | Failed generations | Reported tokens | Observable turns |
|---|---:|---:|---:|---:|
| single | 5 | 0 | 13,976 | 24 |
| consensus | 3 | 0 | 109,637 | 288 |
| self_refine | 8 | 0 | 248,859 | 288 |
| staged | 2 | 0 | 142,524 | 141 |
| direct | 3 | 0 | 37,489 | 48 |

Staged and direct controllers pass 2/24 and 3/24 respectively, compared with
single 5/24. Their paired differences are -0.125 (interval [-0.3333, 0]) and
-0.0833 (interval [-0.2917, 0.0833]). Self-refinement passes 8/24 with difference
+0.125 (interval [-0.1667, 0.375]); consensus passes 3/24 with difference -0.0833
(interval [-0.25, 0]). All intervals retain zero. None proves a positive gain
against single in this study; point estimates do not establish population ranks.

Total reported generation cost is 552,485 tokens / 789 observable model turns,
with no generation failures or unknown calls. Staged costs about 10.2 times
single, direct 2.7 times and self-refinement 17.8 times. Budgets cap workflow
steps, not tokens or USD. Both controllers may stop before exhausting the
allowance; direct used two turns per trial. Low realized cost alone does not
establish quality efficiency. Provider billing and hidden retries remain opaque.

The report's `shared_roster` stratum aggregates its declared roster, which here
contains only Gemini Flash Lite. This is a reduced training-free implementation,
not replication of learned policies in the referenced paper. The oracle remains
evaluator-only. Eight tasks, stochastic repeated calls and unadjusted intervals
limit generalization. The budget-6 study subsequently completed; see its result
and the final selection diagnostics.

No controller enters the stable API based on this result. Final adoption decisions
must include the remaining declared study and final environment verification.

Artifacts: `results/2026-10-04-heldout-v1/meta-gemini-budget12.json`,
`meta-gemini-budget12.protocol.json`, `meta-gemini-budget12.analysis.json` and
`meta-gemini-budget12.terminal.json` in that same directory.
