# BDD Specifications

Gherkin for the two features. These go into `tests/features/` at implementation
time (`ensemble.feature` new; repair additions appended to the existing
`repair.feature`). Step defs live in `tests/test_*_feature.py`, bound via
`scenarios(...)`. `asyncio_mode = auto`; pytest-bdd steps are sync, so `@when`
wraps the engine coroutine in `asyncio.run()` (mirror
`tests/test_repair_feature.py:75`). The LLM is faked at the single seam
`agent_runtime.run_agent`, dispatching on `agent.name` (each arm gets a distinct
stable name, e.g. `Candidate[alpha]`).

Vocabulary is canonical per `_index.md` Glossary: **roster / arm / scorer /
verifier / wider / deeper / policy / candidate**.

## `tests/features/ensemble.feature`

```gherkin
Feature: Heterogeneous ensemble search engine
  The ensemble treats N different models (a roster) as candidate generators and
  ranks their answers with an INJECTED scorer (a ground-truth / value signal).
  It adaptively goes wider (a fresh candidate, possibly from a new arm) or
  deeper (refine the current best), and returns the highest-scoring candidate.
  The scorer is mandatory, so the engine can never degrade into a pure scaffold
  that merely rearranges one model's own thinking.

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

### Roster-distinctness unit test (not via the mocked seam — FR6)

This needs the real `llm_config` resolution path, so it is a focused unit test
rather than a `.feature` scenario (the seam is mocked in BDD, hiding the
fallback). Pseudocode of the intent:

```
Given a roster ["openrouter:qwen3.6-32b", "openrouter:qwen3.6-32b"]   # duplicate
  and OPENROUTER_API_KEY unset (both silently fall back to gemini-3.5-flash)
When the ensemble engine is constructed
Then it warns/errors that the roster collapsed to one effective model
```

## `tests/features/repair.feature` — additions

The three existing scenarios (`tests/features/repair.feature:6-23`) stay verbatim
— that is the back-compat guarantee. Append:

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

## Coverage rationale

- **Ensemble happy path / ranking** — FR1, FR2, FR4.
- **Schedule under injected policy** — FR3 (determinism via injected policy, not
  un-seeded RNG; the realized move trace is a returned value, asserted directly).
- **Cross-model rescue** — the core "one model's miss becomes another's hint"
  mechanism that distinguishes this from same-model best-of-K.
- **Mandatory scorer / conflicting config** — FR2, the honesty guard made
  structural.
- **Budget stop + solved-score short-circuit** — FR5, H1-cost.
- **All-reject best-effort + model-raises tolerance** — robustness; a failed arm
  must not kill the search (mirrors the workflow null-on-failure contract).
- **Repair rotation + attribution + back-compat + cycle** — FR8, FR9, FR10,
  NFR1.
