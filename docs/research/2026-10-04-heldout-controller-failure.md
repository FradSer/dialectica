# Held-out controller failure diagnosis

Observed in the active frozen campaign `2026-10-04-heldout-v1`:
`evidence-heldout-004`, repeat 1, arm `staged`.

The generation receipt ends with `TypeError`, not a judge failure or a
provider exception. The third call (`meta_propose_0`) returned a `run` action
with `artifact_id="artifact-0"`. The declared action contract requires
`artifact_id` to be null for run; input references belong in `context_ids`.
The prompt and schema both state that restriction. Revalidating the saved
raw output against the unchanged `Proposals` schema reproduces the rejection:
`run requires an instruction and cannot submit an artifact`.
The controller rejects the untyped result as `invalid controller response`.

All three model calls returned successfully. Their recorded usage sums to
1,919 prompt tokens, 535 output tokens and 2,454 total tokens, with three
observable model turns and zero unknown calls. The receipt's zero call failures
counts model-call errors; its nonempty top-level error records the orchestration
failure. These are distinct outcomes.

All three baseline comparisons preserve `generation_failed`, with no winner.
No retry, replacement result or imputed tie was introduced. This is one observed
structured-controller failure, not evidence of a general failure rate or a
failure-accounting defect. The frozen code, dependencies and source archive
were verified unchanged during diagnosis. Full-study analysis remains pending.
