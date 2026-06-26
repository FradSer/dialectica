# Task 004 — Honesty-gate ablation harness (3-arm + repair sub-criterion)

**type:** eval
**depends-on:** ["002-impl", "003-impl"]

Ship the non-negotiable honesty gate as a reproducible eval harness, mirroring
`evals/repair_ablation.py` / `evals/workflow_ablation.py`. This is the
KEEP-vs-CUT decision instrument; the feature is on probation until this runs.

## Files to create

- `evals/ensemble_ablation.py` (new).

## BDD Scenario

None — this is a dev harness (not shipped in the wheel), consistent with the
existing `evals/*` ablations which are not BDD-scenario-driven. Its acceptance is
the functional contract below, not a Gherkin scenario. (This is the one task in
the plan with no scenario, by design — the design `_index.md` success-criteria
section specifies it as the honesty gate, and the repo's other ablations follow
the same no-Gherkin convention.)

## What to implement (what, not how)

1. **Three arms at matched total LLM-call cost**, counted through the single seam
   via `evals.harness.count_agent_calls` (so cost is measured identically to the
   other ablations):
   - **(a) ensemble + signal** — `create_ensemble_engine(problem, scorer=<real>,
     models=<roster>, max_calls=N)`.
   - **(b) best-single best-of-N** — best-of-N on the strongest single roster
     member (ensemble degenerate N=1, or a plain best-of-N loop), same total
     call budget N.
   - **(c) ensemble blind-pick** — the same N heterogeneous candidates, signal
     replaced by random/blind pick (the no-signal control).
2. **KEEP / CUT logic** — print the per-arm primary metric (pass-rate on
   verifiable tasks; net wins via the blind position-swapped judge for meta-tasks)
   AND the call counts. KEEP only if (a) > (b) AND (a) > (c) by a signal-attributable
   margin; report a cheaper (a)≈(b) tie as a secondary note; otherwise report CUT
   honestly (consistent with the dialectic/ToT negative results).
3. **Repair sub-criterion** — also compare multi-model-repair@K vs
   single-model-repair@K on a verifiable set, using the FR10 `history["model"]`
   attribution to confirm wins came from model-switching, not extra same-model
   attempts.
4. **CLI** — `uv run python -m evals.ensemble_ablation [--limit N --json out.json]`,
   matching the other ablations' argument shape; reuse `evals/baseline.py`,
   `evals/judge.py`, and an existing problem set (e.g. `evals/problems.py` /
   `evals/meta_problems.py`) rather than inventing one.

Reuse existing harness components; no new public library API. This task adds an
eval dev tool only — it does not modify `dialectica/`.

## Verification

```bash
# Structural / offline checks (no API key; real run is operator-driven):
uv run python -c "import evals.ensemble_ablation"   # imports cleanly
uv run ruff format --check evals/ensemble_ablation.py
uv run ruff check evals/ensemble_ablation.py
uv run python -m evals.ensemble_ablation --help     # CLI wired
```

A real scored run (`uv run python -m evals.ensemble_ablation --limit ...` with
`GOOGLE_API_KEY` + a multi-provider roster) is the operator-run honesty gate that
decides KEEP vs CUT; it is not part of automated CI verification.
