# Early claim-study failures

These observations belong to the running frozen `claims-gemini-k6` study,
not a completed-study estimate. Saved raw outputs were revalidated without
new model calls or changes to frozen sources/dependencies.

- `portfolio-heldout-000`, repeat 0, consensus: the fifth candidate exceeds
  the declared exactly-five-claims schema (`claims: too_long`), causing the
  baseline's typed-output guard to reject it. A prior candidate also has a
  bare-list answer rather than the required selected-key JSON object. The
  terminating failure is the fifth candidate's schema rejection, not that
  earlier answer parse failure. Five successful model turns cost 3,875 tokens.
- Same task, repeat 1, single: the candidate satisfies the outer claim schema,
  but its answer is a long reasoning paragraph instead of a parseable JSON
  object with `selected`. The prediction parser rejects it; with no parsed
  candidate the selector raises ValueError. One successful turn costs 1,258
  tokens.

Both receipts reconcile their usage with all underlying records and report
zero unknown calls. Their top-level errors record workflow failure even though
individual model calls returned successfully. The preset trial outcome is
preserved; no hidden retries, answer extraction by hindsight or candidate
replacement was introduced. Final analysis must count failed trials in the
complete paired pool, rather than report only successfully parsed outputs.

Evidence: `results/2026-10-04-heldout-v1/claims-gemini-k6.json`.
