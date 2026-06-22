Feature: Matched-compute quality controls
  To test whether an adversarial engine's tree structure raises quality (not
  just its compute or its prompt), the ablation pits it against two flat
  baselines at matched call budget: best-of-N + a selector, and K-round
  self-refine. These scenarios pin down their cost and selection behavior with
  a mocked LLM, so the live run's "matched compute" claim is grounded.

  Scenario: Best-of-N samples N candidates and returns the model's pick
    Given a mocked LLM that returns numbered candidates and picks candidate 2
    When best-of-N runs with n 3
    Then it makes 4 LLM calls
    And it returns the second candidate

  Scenario: Self-refine runs the critique-improve loop K times
    Given a mocked LLM that drafts, critiques, and improves
    When self-refine runs with 2 rounds
    Then it makes 5 LLM calls
    And it returns the final improved solution
