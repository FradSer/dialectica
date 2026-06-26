# Task 002 — Ensemble search engine: BDD scenarios (Red)

**type:** test
**depends-on:** ["001"]

Write the failing executable specification for `EnsembleSearchEngine`. These
tests MUST fail (Red) against the signature-only `ensemble.py` from task 001 —
that is the proof they exercise real behavior before task 003 implements it.

## Files to create / modify

- `tests/features/ensemble.feature` (new) — the 8 scenarios below, verbatim from
  the design `bdd-specs.md`.
- `tests/test_ensemble_feature.py` (new) — pytest-bdd step definitions bound via
  `scenarios("features/ensemble.feature")`. Steps are sync; wrap the engine
  coroutine in `asyncio.run()` in the `@when`. Use the heterogeneous-model fake
  from `tests/helpers.py` (task 001), patching only `agent_runtime.run_agent`.
  Scorer / verifier / policy are pure Python closures built in the steps. Assert
  the realized wider/deeper move sequence from the returned trace
  (`result["history"]` / `result["moves"]`), never from logs.
- `tests/test_ensemble_feature.py` (same file) — also add the **FR6
  roster-distinctness unit test** (a plain pytest function, NOT a `.feature`
  scenario, because it needs the real `llm_config` fallback path that the mocked
  seam hides): constructing a roster whose members all resolve to the same
  effective model (duplicate config + unset provider key) warns/errors.

## BDD Scenario

```gherkin
Feature: Heterogeneous ensemble search engine

  Background:
    Given a roster of three models "alpha", "beta", and "gamma"

  Scenario: The highest-scoring candidate across models wins
    Given each model produces a candidate the scorer rates alpha=0.4 beta=0.9 gamma=0.6
    And a max-calls budget of 3
    When the ensemble searches
    Then the winning answer is the one from model "beta"
    And the winning score is 0.9

  Scenario: The schedule alternates wider and deeper under an injected policy
    Given a deterministic policy scripted as "wider, deeper, wider"
    And every candidate the scorer can rate
    And a max-calls budget of 3
    When the ensemble searches
    Then the move sequence taken was "wider, deeper, wider"
    And a wider move sampled a not-yet-used model
    And a deeper move re-prompted the current best model

  Scenario: A weak candidate from one model is rescued by another going wider
    Given model "alpha" produces a candidate the scorer rates 0.2
    And going deeper on "alpha" cannot exceed 0.3
    And model "beta" produces a candidate the scorer rates 0.85 when sampled wider
    And a max-calls budget of 4
    When the ensemble searches
    Then the winning answer is the one from model "beta"
    And the winning score is at least 0.85

  Scenario: The scorer is mandatory
    When an ensemble engine is constructed without a scorer
    Then construction fails with a missing-scorer error

  Scenario: Search stops at the max-calls budget and returns best-so-far
    Given a roster that would keep producing candidates indefinitely
    And the best candidate seen within budget scores 0.7
    And a max-calls budget of 2
    When the ensemble searches
    Then the engine made exactly 2 model calls
    And the returned answer is the best-so-far scoring 0.7
    And the result reports passed is false

  Scenario: Solved score short-circuits before the budget is spent
    Given model "alpha" produces a candidate the scorer rates 1.0
    And a max-calls budget of 5
    When the ensemble searches
    Then the result reports passed is true
    And the engine made exactly 1 model call

  Scenario: Every candidate is rejected — best-effort is returned, not an error
    Given every model produces a candidate the scorer rates 0.0
    And a max-calls budget of 3
    When the ensemble searches
    Then the search reports it did not find a satisfactory answer
    And it still returns the best-effort candidate rather than raising

  Scenario: A model that raises is treated as a failed candidate, not a crash
    Given model "beta" raises when called
    And models "alpha" and "gamma" produce candidates rated 0.5 and 0.8
    And a max-calls budget of 3
    When the ensemble searches
    Then the search completes without raising
    And the winning answer is the one from model "gamma"
    And the failed model "beta" is recorded as a failed candidate
```

Plus (non-Gherkin, same test module):

```
FR6 roster-distinctness unit test:
  Given a roster ["openrouter:qwen3.6-32b", "openrouter:qwen3.6-32b"]   # duplicate
    and OPENROUTER_API_KEY unset (both silently fall back to gemini-3.5-flash)
  When the ensemble engine is constructed
  Then it warns or errors that the roster collapsed to one effective model
```

## Steps (what, not how)

1. Write `tests/features/ensemble.feature` with the 8 scenarios above.
2. Write `tests/test_ensemble_feature.py`: bind scenarios; implement the
   Given/When/Then steps using the task-001 fake; inject a scripted deterministic
   policy for the schedule scenario; build scorers as dict-backed closures.
3. Add the FR6 roster-distinctness unit test as a plain async/sync pytest
   function in the same module (manipulate env via monkeypatch; assert on the
   warning/error).
4. Confirm the suite is **Red** (fails because `run()` is unimplemented).

## Verification

```bash
uv run pytest tests/test_ensemble_feature.py -q   # MUST fail (Red) — run() unimplemented
uv run ruff check tests/test_ensemble_feature.py
```

A Red result here (assertion/NotImplementedError failures, not collection
errors) is the success condition for this task. Collection/import errors mean the
task-001 contracts are wrong — fix those, do not stub the test.
