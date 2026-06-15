Feature: Dialectical kernel
  The soul kernel runs thesis -> antithesis -> synthesis intelligently: it
  names the problem's core tension first, skips the dialectic when there is
  none, opposes with a complete rival, and spirals until the opposition is
  exhausted.

  Scenario: A determinate problem skips the dialectic entirely
    Given a dialectic engine
    And the problem has no genuine tension
    When the dialectic runs
    Then it is not dialecticized
    And the answer is the direct thesis
    And no antithesis was raised

  Scenario: A genuine tension drives the thesis-antithesis-synthesis spiral
    Given a dialectic engine
    And the problem's core tension is "Speed vs Safety"
    And each synthesis surpasses its thesis
    When the dialectic runs
    Then it is dialecticized
    And the trace identifies the tension before the thesis
    And the answer is the final synthesis

  Scenario: Convergence is semantic — the adversary concedes, not the score
    Given a dialectic engine with max rounds 3
    And the problem's core tension is "Centralize vs Distribute"
    And the opposition is exhausted after 1 round
    When the dialectic runs
    Then it is dialecticized
    And the dialectic ran 1 round
    And convergence was by exhaustion, not by reaching max rounds

  Scenario: Scoring judges the solution against the problem, not in a vacuum
    Given a dialectic engine
    And the problem's core tension is "Speed vs Safety"
    And each synthesis surpasses its thesis
    When the dialectic runs
    Then every scoring call saw the problem statement
