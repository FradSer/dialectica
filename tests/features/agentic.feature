Feature: Agentic engine
  The agentic engine adds capability a single forward pass lacks: it equips the
  model with injected tools and runs a tool-using loop until the task is done.
  The tools are injected by the caller, so the engine stays task-agnostic.

  Scenario: The engine equips the agent with the injected tools and runs it
    Given an agentic engine for a task with a probe tool
    When the agent completes the task
    Then it returns the agent's final answer
    And the agent was given the probe tool
    And the agent is instructed to use tools rather than guess
