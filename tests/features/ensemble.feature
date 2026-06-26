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
