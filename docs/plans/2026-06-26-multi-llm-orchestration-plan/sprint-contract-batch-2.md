# Sprint Contract — Batch 2: Multi-model repair (task 003)

**Scope:** Extend `dialectica/repair.py` with an optional model roster that
rotates on failure. Red→Green.
- Task 003-test (Red): append 4 scenarios to `tests/features/repair.feature`
  (existing 3 untouched) + step defs in `tests/test_repair_feature.py`.
- Task 003-impl (Green): `IterativeRepairEngine` accepts a generator list,
  rotates round-robin per attempt, records `history[i]["model"]`;
  `create_repair_engine` gains `models` (mutually exclusive with `model_config`
  → ValueError).

**Definition of done:** `uv run pytest tests/test_repair_feature.py -q` green
(original 3 + 4 new), full `uv run pytest -q` green, ruff clean. Back-compat:
single-model path byte-identical when `models` omitted. Confirm RED then GREEN.

**Out of scope:** ensemble (batch 1, done), evals (batch 3).
