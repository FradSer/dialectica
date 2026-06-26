# Sprint Contract — Batch 1: Ensemble engine (tasks 001 + 002)

**Scope:** Foundation + the full ensemble Red→Green cycle.
- Task 001 (setup): `dialectica/ensemble.py` contracts, `__init__.py` exports +
  version bump, heterogeneous-model test fake in `tests/helpers.py`.
- Task 002-test (Red): `tests/features/ensemble.feature` (8 scenarios) +
  `tests/test_ensemble_feature.py` + FR6 roster-distinctness unit test.
- Task 002-impl (Green): `EnsembleSearchEngine` + default Thompson policy +
  `create_ensemble_engine`.

**Definition of done:** `uv run pytest tests/test_ensemble_feature.py -q` green
(incl. FR6 unit test), full `uv run pytest -q` green (no regressions),
`uv run ruff format --check` + `uv run ruff check` clean on changed files,
imports resolve. Coordinator must confirm RED (tests fail before impl) then GREEN.

**Out of scope:** repair.py (batch 2), evals (batch 3).
