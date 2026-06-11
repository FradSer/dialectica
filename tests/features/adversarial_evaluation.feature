Feature: GAN adversarial evaluation
  Each thought is judged by a Discriminator; below the threshold the
  Generator refines it and the loop re-scores, keeping the best round
  (thesis -> antithesis -> synthesis).

  Scenario: A passing score on the first round skips refinement
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns scores "8.0"
    When the evaluator judges "a thought"
    Then the result score is 8.0
    And the loop ran 1 round
    And the refined thought is "a thought"

  Scenario: A low score triggers refinement and re-scoring
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns scores "5.0, 9.0"
    And the generator refines thoughts to "REFINED"
    When the evaluator judges "a thought"
    Then the result score is 9.0
    And the loop ran 2 rounds
    And the refined thought is "REFINED"

  Scenario: Refinement that degrades the thought keeps the best round
    Given an adversarial evaluator with max rounds 2 and score threshold 9.0
    And the discriminator returns scores "7.5, 3.0"
    And the generator refines thoughts to "WORSE VERSION"
    When the evaluator judges "original thought"
    Then the result score is 7.5
    And the loop ran 2 rounds
    And the refined thought is "original thought"

  Scenario: The discriminator can terminate a branch early
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns score 2.0 with termination
    When the evaluator judges "a thought"
    Then the evaluation requests termination
    And the loop ran 1 round

  Scenario: Custom evaluation criteria reach the discriminator
    Given an adversarial evaluator with custom criteria "JUDGE ONLY ON COST"
    And the discriminator returns scores "8.0"
    When the evaluator judges "a thought"
    Then the discriminator was instructed with "JUDGE ONLY ON COST"

  Scenario: A verdict with invalid string escapes is repaired
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns a verdict with invalid escapes and score 8.0
    When the evaluator judges "a thought"
    Then the result score is 8.0
    And the loop ran 1 round

  Scenario: A verdict wrapped in a markdown code fence is accepted
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns a fenced verdict with score 8.0
    When the evaluator judges "a thought"
    Then the result score is 8.0
    And the loop ran 1 round

  Scenario: A transiently unparseable verdict is re-asked, not scored zero
    Given an adversarial evaluator with max rounds 3 and score threshold 7.0
    And the discriminator returns malformed output once and then score 8.0
    When the evaluator judges "a thought"
    Then the result score is 8.0
    And the loop ran 1 round

  Scenario: Persistently unparseable verdicts abort instead of burning budget
    Given an adversarial evaluator with max rounds 5 and score threshold 7.0
    And the discriminator always returns malformed output
    When the evaluator judges "a thought" expecting failure
    Then the evaluation aborts after 3 consecutive unparseable verdicts
