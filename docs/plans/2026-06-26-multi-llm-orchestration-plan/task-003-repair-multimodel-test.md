# Task 003 — Multi-model repair: BDD scenarios (Red)

**type:** test
**depends-on:** ["001"]

Write the failing executable specification for the multi-model repair extension.
The three existing repair scenarios (`tests/features/repair.feature:6-23`) stay
verbatim — that is the back-compat guarantee these new tests protect.

## Files to modify

- `tests/features/repair.feature` — append the 4 scenarios below. Do NOT touch
  the existing three.
- `tests/test_repair_feature.py` — add step definitions for the new scenarios.
  Reuse the heterogeneous-model fake from `tests/helpers.py` (task 001) for the
  roster steps; reuse the existing single-model fakes for the back-compat
  scenario. Steps are sync; wrap `engine.run()` in `asyncio.run()`. Assert
  per-attempt model attribution against the returned `history` (each entry must
  carry a `model`).

## BDD Scenario

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

  Scenario: Single-model repair is unchanged when no roster is given
    Given a repair engine whose first solution fails then is fixed
    When the repair engine runs
    Then the solution passed
    And it took 2 attempts
    And every attempt was produced by the same single model

  Scenario: The roster cycles back when failures exceed the roster size
    Given a repair engine whose generator is a roster of models "A" and "B"
    And max 3 attempts where no model ever passes the verifier
    When the repair engine runs
    Then the solution did not pass
    And it took 3 attempts
    And the attempts were produced by models "A", "B", "A" in order

  Scenario: Passing model_config and models together is rejected
    When a repair engine is created with both model_config and models set
    Then construction fails with a conflicting-config error
```

## Steps (what, not how)

1. Append the 4 scenarios to `tests/features/repair.feature`.
2. Add step defs in `tests/test_repair_feature.py`: a roster-backed repair engine
   built via `create_repair_engine(..., models=["A","B"])`; a verifier closure
   scripted per scenario; the "same single model" assertion reuses the existing
   `Given a repair engine whose first solution fails then is fixed` step plus a
   new `Then every attempt was produced by the same single model`.
3. Confirm the new scenarios are **Red** (fail because `models=` /
   rotation / `history["model"]` / the conflicting-config `ValueError` are not
   implemented yet) while the original three stay green.

## Verification

```bash
uv run pytest tests/test_repair_feature.py -q   # original 3 green; 4 new Red (unimplemented)
uv run ruff check tests/test_repair_feature.py
```

Red on the four new scenarios (not collection errors) is this task's success
condition.
