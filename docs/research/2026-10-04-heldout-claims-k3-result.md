# Completed held-out claim study: Gemini K=3

Third of seven frozen studies completed: 8 held-out portfolio tasks × 3 repeats
× 4 arms = 96 trials. Terminal report/protocol/analysis hashes were verified;
task/configuration bindings agree, and frozen sources/dependencies remain
unchanged. Failed generation counts as an incorrect system outcome.

| Arm | Correct / 24 | Failed generations | Reported tokens | Observable turns |
|---|---:|---:|---:|---:|
| single | 3 | 5 | 17,949 | 24 |
| consensus | 3 | 3 | 85,006 | 135 |
| self_refine | 7 | 1 | 113,926 | 140 |
| claims | 7 | 1 | 90,716 | 144 |

Claims and self-refinement each pass 7/24 versus single and consensus 3/24.
Claims-versus-single difference is +0.1667, with exploratory paired task-bootstrap
interval [0, 0.4167]; self-refinement interval is [-0.0417, 0.375]. Both retain
zero. Consensus has an observed difference of zero and a degenerate bootstrap
interval; this does not prove equivalence beyond the observed task pool.

The complete study reports 307,597 tokens / 443 observable turns, including
10 failed generations, with zero unknown calls. Claim cost is about 5.1 times
single. Workflow-step budgets do not imply token or USD parity; provider billing
and hidden retries remain opaque.

Together with K=6 (claims 6/24; self-refinement 7/24), these results do not show
a clear monotonic claim-selection gain from increased budget. Independent
stochastic calls, unequal realized costs and eight observed tasks limit that
cross-study interpretation. There is no formal paired cross-budget interval
or direct claims-versus-self-refinement superiority interval here. The
same-candidate ablation is interpreted in the final selection diagnostics: no
correctness change from claim weighting on 23 observed trials. Strong-model
controls and staged/direct studies subsequently completed; see the completion audit.

Claim falsification remains a research example. This study alone does not
justify stable API promotion. Intervals are exploratory, conditional on the
observed task pool and unadjusted for multiple comparisons.

Artifacts: `results/2026-10-04-heldout-v1/claims-gemini-k3.json`,
`claims-gemini-k3.protocol.json`, `claims-gemini-k3.analysis.json` and
`claims-gemini-k3.terminal.json` in that same directory.
