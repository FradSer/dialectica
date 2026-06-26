# Handoff Summary — Batch 3 (honesty-gate ablation harness)

**Status:** COMPLETE. Task 004 done.

**Delivered:**
- `evals/ensemble_ablation.py` — three arms at matched LLM-call cost (counted via
  `count_agent_calls`): (a) ensemble + real ground-truth scorer, (b) best-single
  best-of-N on the strongest roster member, (c) ensemble blind-pick (constant
  scorer). KEEP only if (a) > (b) AND (a) > (c); cheaper (a)≈(b) tie is a
  secondary note. H1 stated in the module docstring. Repair sub-criterion:
  multi-model-repair@K vs single@K, attribution via `history["model"]`.
  CLI: `--budget --limit --json --problems {novel,hard}`.

**Verification (independently re-run):** imports clean, `--help` works, ruff
clean, full suite 133 passing. A real scored run is operator-driven (needs
`GOOGLE_API_KEY` + multi-provider roster) and is excluded from CI by design.

All 6 plan tasks complete.
