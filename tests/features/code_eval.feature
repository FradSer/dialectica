Feature: SWE code eval
  Mainstream HumanEval-style benchmark: each problem is a Python function
  specification with hidden unit tests. The engine and a single-call baseline
  each produce an implementation; verification runs the tests in a subprocess,
  so pass/fail is ground truth — no LLM judge involved.

  Scenario: Code is extracted from a fenced answer
    Given an answer containing a python code block among prose
    When the code is extracted
    Then the extracted code contains the function definition only

  Scenario: A correct solution passes verification
    Given the code problem "add_two"
    When a correct implementation is verified
    Then the verification passes

  Scenario: An incorrect solution fails verification
    Given the code problem "add_two"
    When an incorrect implementation is verified
    Then the verification fails

  Scenario: A solution that loops forever fails by timeout
    Given the code problem "add_two"
    When a non-terminating implementation is verified
    Then the verification fails

  Scenario: The code eval report tallies ground-truth pass rates
    Given a mocked LLM whose engine answers are correct and baseline answers are wrong
    When the code eval runs on 2 problems
    Then the engine pass rate is 2 of 2
    And the baseline pass rate is 0 of 2

  Scenario: Rescue mode runs the engine only on baseline failures
    Given a mocked LLM where the baseline only solves the addition problem
    When the rescue eval runs on the addition and subtraction problems
    Then the baseline screen solves 1 problem
    And the engine attempts 1 problem
    And the rescue count is 1
