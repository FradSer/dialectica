Feature: Workflow orchestration primitives
  A composable multi-agent runtime (agent/parallel/pipeline/phase/log/budget)
  for meta-task workflows — research, review, planning, design. Built on the
  repo's single LLM seam so the existing mock, retry, and concurrency cap
  apply. This is an orchestration layer, NOT a self-contained-quality engine.

  Scenario: parallel waits for all and converts a failed thunk to null
    Given a mocked LLM that returns a string per call and fails on "bad"
    When parallel runs three thunks including a failing one
    Then it returns three results with the failed one null
    And the other two are their strings

  Scenario: pipeline runs each item through all stages with no barrier
    Given a mocked LLM and an increment stage
    When pipeline runs three items through two stages
    Then each item reaches the final stage independently

  Scenario: a pipeline stage that throws drops only that item
    Given a mocked LLM and a stage that throws on item index 1
    When pipeline runs three items
    Then item 0 and item 2 survive and item 1 is null

  Scenario: agent with a schema returns a validated model instance
    Given a mocked LLM that returns valid JSON for a schema
    When agent runs with the schema
    Then it returns a validated instance with the fields

  Scenario: agent without a schema returns the raw text
    Given a mocked LLM that returns prose
    When agent runs without a schema
    Then it returns the raw text

  Scenario: agent with a schema returns null after repeated parse failures
    Given a mocked LLM that always returns unparseable JSON
    When agent retries a schema on unparseable output
    Then it returns null

  Scenario: agent parses a JSON object wrapped in narration and a fence
    Given a mocked LLM that returns a fenced JSON object inside prose
    When agent parses the fenced response with the schema
    Then the fenced response yields a validated instance

  Scenario: agent raises BudgetExhausted when the budget is spent
    Given a mocked LLM and a budget of one call
    When agent runs a second time after the first consumes the budget
    Then it raises BudgetExhausted

  Scenario: phase and log record into the run context
    Given a workflow script that phases and logs
    When the workflow runs
    Then the phases and log are captured on the run

  Scenario: agent wires injected tools into the underlying agent
    Given a mocked LLM that records the agent it receives
    When agent runs with a tool injected
    Then the underlying agent carries that tool

  Scenario: agent rejects combining tools with schema
    When agent runs with both tools and a schema
    Then it raises ValueError naming the ADK conflict

  Scenario: agent injects instructions into the underlying agent's system prompt
    Given a mocked LLM that records the agent it receives
    When agent runs with instructions injected
    Then the underlying agent's instruction contains the injected text

  Scenario: agent resolves a provider:model override before building the agent
    Given a mocked LLM that records the agent it receives
    When agent runs with a provider-prefixed model override
    Then the underlying agent's model is the resolved model name
