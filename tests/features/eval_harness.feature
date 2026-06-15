Feature: Eval harness
  Answers "is the engine worth its cost" with data: each benchmark problem is
  solved by the engine and by a single-call baseline, then a blind LLM judge
  compares the two answers without knowing which is which. Position bias is
  neutralized by judging twice with swapped positions; disagreement is a tie.

  Scenario: A judge with a consistent preference declares a winner
    Given a blind judge whose model always prefers the engine answer
    When the judge compares an engine answer and a baseline answer
    Then the comparison winner is "engine"

  Scenario: A position-biased judge yields a tie
    Given a blind judge whose model always prefers position A
    When the judge compares an engine answer and a baseline answer
    Then the comparison winner is "tie"

  Scenario: A malformed judge verdict yields a tie
    Given a blind judge whose model returns malformed verdicts
    When the judge compares an engine answer and a baseline answer
    Then the comparison winner is "tie"

  Scenario: An empty verdict is re-asked, not silently counted as a tie
    Given a blind judge whose model returns an empty verdict once, then prefers the engine
    When the judge compares an engine answer and a baseline answer
    Then the comparison winner is "engine"

  Scenario: The harness reports answers, costs and verdicts per problem
    Given an eval harness with a mocked LLM that favors the engine
    When the harness evaluates 1 problem
    Then the report has 1 result with both answers
    And the engine used more LLM calls than the baseline
    And the aggregate shows 1 engine win

  Scenario: Agent calls are counted through the runtime seam
    Given a mocked LLM
    When 3 agent calls run inside the call counter
    Then the counter reports 3 calls
