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

  Scenario: Repair inside a workflow script charges the outer budget
    Given a repair engine whose first solution fails then is fixed
    When the repair engine runs inside an outer workflow with a budget of three calls
    Then the solution passed
    And it took 2 attempts
    And the outer budget records 2 calls spent

  Scenario: Repair that exhausts the outer workflow budget raises BudgetExhausted
    Given a repair engine with max 2 attempts whose solution never passes
    When the repair engine runs inside an outer workflow with a budget of one call
    Then the outer workflow raises BudgetExhausted
