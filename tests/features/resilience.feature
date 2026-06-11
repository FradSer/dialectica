Feature: LLM call resilience
  An engine run is hundreds of sequential LLM calls; the runtime retries
  transient failures with exponential backoff instead of letting a single
  network error destroy the whole run. Persistent failures still surface.

  Scenario: Transient LLM failures are retried instead of killing the run
    Given an LLM transport that fails 2 times before succeeding
    When an agent call runs through the runtime
    Then the call succeeds after 3 attempts

  Scenario: A persistent LLM failure still surfaces
    Given an LLM transport that always fails
    When an agent call runs through the runtime
    Then the call fails after exhausting 3 attempts
