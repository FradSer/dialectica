Feature: Execution-guided repair engine
  On verifiable tasks the engine closes the loop a single forward pass cannot:
  it runs the candidate against an objective verifier and repairs against the
  concrete failure, until the verifier passes or attempts run out.

  Scenario: A passing first solution returns immediately
    Given a repair engine whose first solution passes
    When the repair engine runs
    Then the solution passed
    And it took 1 attempt

  Scenario: A failing solution is repaired against the verifier feedback
    Given a repair engine whose first solution fails then is fixed
    When the repair engine runs
    Then the solution passed
    And it took 2 attempts
    And the repair prompt carried the verifier feedback

  Scenario: Repair gives up after exhausting its attempts
    Given a repair engine with max 2 attempts whose solution never passes
    When the repair engine runs
    Then the solution did not pass
    And it took 2 attempts
