# Sprint Contract — Batch 3: Honesty-gate ablation harness (task 004)

**Scope:** Create `evals/ensemble_ablation.py` — the 3-arm honesty gate
(ensemble+signal / best-single best-of-N / ensemble blind-pick) at matched call
cost, plus the repair sub-criterion (multi-model-repair@K vs single@K via
`history["model"]` attribution). CLI matching the other ablations.

**Definition of done:** offline-verifiable only (no API key in CI) —
`uv run python -c "import evals.ensemble_ablation"` imports clean,
`uv run python -m evals.ensemble_ablation --help` shows the CLI,
`uv run ruff format --check` + `uv run ruff check` clean, full
`uv run pytest -q` still green (133). Dev tool; no BDD scenario.

**Out of scope:** any change to `dialectica/` (engines are done and accepted).
