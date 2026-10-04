# Completed strong-model meta single control

Fourth of seven frozen studies completed. GPT-5.5 single solves all 24 trials
(8 held-out portfolio tasks × 3 repeats), with no generation failures and zero
unknown calls. Reported cost is 39,495 tokens / 24 observable model turns,
mean 1,645.625 tokens per trial. Terminal report/protocol/analysis byte hashes
and task/configuration bindings were checked, as were all per-record usage
sums and the campaign's unchanged sources/dependencies/archive.

This is an observed ceiling on the declared task pool. The degenerate task-
bootstrap interval [1, 1] does not establish certainty on unseen tasks. No
staged/direct or claim-falsification strong-model arm was declared, so this
control provides no evidence for their benefit on GPT. The separate claim-
format GPT control is still running; it must not be conflated with this output
contract. Actual costs are reported, not matched tokens or provider billing.

The objective study's `shared_roster` stratum means it aggregates the declared
roster for that report; the frozen configuration here contains only GPT-5.5.
Do not interpret it as an additional model or multi-model experiment.

Artifacts: `results/2026-10-04-heldout-v1/strong-meta-single.json`,
`strong-meta-single.protocol.json`, `strong-meta-single.analysis.json` and
`strong-meta-single.terminal.json` in that same directory.

Three campaign studies and final environment verification remain. This control
does not justify a new stable API or a universal single-call superiority claim.

## Subsequent completion

All seven studies subsequently completed. Earlier pending/running statements
above describe the checkpoint when this study finished. See
[the completion audit](2026-10-04-completion-audit.md) for final environment
verification and [selection diagnostics](2026-10-04-heldout-selection-diagnostics.md)
for candidate coverage and same-candidate comparisons. The frozen raw artifacts
and declared analyses remain unchanged.
