# Task 003 — Multi-model repair: implementation (Green)

**type:** impl
**depends-on:** ["003-test"]

Extend `IterativeRepairEngine` and `create_repair_engine` with an optional model
roster that rotates on failure, making the task-003 scenarios Green while keeping
the existing single-model behavior byte-identical.

## Files to modify

- `dialectica/repair.py` only.

## BDD Scenario

Representative (full set in `task-003-repair-multimodel-test.md`):

```gherkin
Scenario: A roster switches model after a verifier failure
  Given a repair engine whose generator is a roster of models "A" and "B"
  And model "A" produces a solution that fails the verifier
  And model "B" produces a solution that passes the verifier
  When the repair engine runs
  Then the solution passed
  And it took 2 attempts
  And attempt 1 was produced by model "A"
  And attempt 2 was produced by model "B"
```

## What to implement (what, not how)

1. **`IterativeRepairEngine.__init__`** — accept `generator` as either a single
   agent (today) or a list of agents, normalizing internally to a list so a
   single agent and a one-element roster take the same path. With one element,
   behavior is byte-identical to today (back-compat).
2. **`run()`** — select the generator per attempt by round-robin rotation over
   the roster (attempt 1 uses the first member). Record the producing model
   config in each `history` entry (`history[i]["model"]`); keep the existing
   `{final_answer, passed, attempts, history}` keys intact.
3. **`create_repair_engine`** — add optional `models: list[str] | None = None`
   after `solution_format`. `models is None` → today's single-generator path,
   unchanged. `models` given → build one Generator agent per config and pass the
   list. `model_config` and `models` both set → raise `ValueError`
   (conflicting-config), satisfying that scenario.
4. **Docstrings** — cross-reference the ensemble engine: repair = deeper-only
   round-robin rotation with a boolean verifier; ensemble = adaptive wider+deeper
   over a roster with a float scorer.

Signature additions only at the public boundary (`models=`); no other API
changes. No new bodies beyond rotation/attribution/validation.

## Verification

```bash
uv run pytest tests/test_repair_feature.py -q   # all green (original 3 + 4 new)
uv run pytest -q                                 # full suite green (no regressions)
uv run ruff format --check dialectica/repair.py
uv run ruff check dialectica/repair.py
```
