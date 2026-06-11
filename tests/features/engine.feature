Feature: Tree-of-Thoughts engine
  The coordinator explores a thought tree in three phases — Initialize,
  Explore (beam-search loop), Synthesize — keeping only thoughts that
  beat the score threshold.

  Scenario: High-scoring thoughts build a full tree and synthesize
    Given the default pipeline with max depth 2 and beam width 2
    And every thought is scored 8.0
    When the engine runs
    Then the final answer is "FINAL SYNTHESIZED ANSWER"
    And the tree contains 10 thoughts
    And the best path starts at the root

  Scenario: Low-scoring thoughts prune the beam
    Given the default pipeline with max depth 2 and beam width 2
    And every thought is scored 3.0
    When the engine runs
    Then the beam is empty
    And the final answer is "FINAL SYNTHESIZED ANSWER"

  Scenario: Sibling thoughts are evaluated concurrently
    Given the default pipeline with max depth 2 and beam width 2
    And every thought is scored 8.0
    When the engine runs with a concurrency probe
    Then at least 2 LLM calls were in flight simultaneously
    And the tree contains 10 thoughts
