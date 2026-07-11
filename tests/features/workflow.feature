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

  Scenario: the concurrency cap gates each agent call directly
    Given a mocked LLM that records calls in flight
    When three agent calls run concurrently under a cap of one
    Then no more than one LLM call was ever in flight

  Scenario: a waiting pipeline item does not hold a concurrency slot
    Given a concurrency cap of one and a pipeline item that waits for its sibling
    When the pipeline runs both items
    Then both items complete because waiting held no slot

  Scenario: the budget meters API-reported token usage
    Given a mocked LLM that reports token usage on each response
    When two agent calls run in a workflow
    Then the budget records the summed prompt, output, and total tokens

  Scenario: a token budget raises BudgetExhausted when output tokens run out
    Given a mocked LLM that reports token usage on each response
    When a second agent call starts after the first spends the token budget
    Then the token budget raises BudgetExhausted

  Scenario: a plain-string response leaves the token meter at zero
    Given a mocked LLM that returns prose
    When two agent calls run with plain-string responses
    Then the budget records zero tokens spent

  Scenario: schema re-asks meter every underlying call
    Given a mocked LLM that returns unparseable JSON with token usage
    When agent retries a schema on usage-reporting responses
    Then the budget records the token usage of every re-ask

  Scenario: workflow standalone opens a fresh run context
    Given a mocked LLM
    When workflow runs a script standalone
    Then the script result is returned
    And the run used one agent call

  Scenario: workflow inside an outer script charges the outer budget
    Given a mocked LLM
    When a child workflow runs inside an outer workflow with a budget of two calls
    Then the outer budget records 2 calls spent

  Scenario: nested workflow inside a child raises
    Given a mocked LLM
    When workflow is called inside a child workflow
    Then it raises a nesting limit error

  Scenario: workflow passes args to the child script
    Given a mocked LLM
    When workflow runs with args inside an outer workflow
    Then the child script reads the passed args

  Scenario: parallel rejects more than 4096 thunks
    When parallel runs 4097 thunks
    Then it raises an item cap error

  Scenario: the lifetime agent cap rejects the 1001st agent call
    Given a mocked LLM
    When agent is called 1001 times in one run
    Then it raises WorkflowAgentCapExceeded

  Scenario: a registered workflow name resolves through workflow
    Given a mocked LLM and a registered workflow "demo"
    When workflow runs the registered name
    Then the registered script result is returned

  Scenario: meta phase titles must match phase calls
    Given a mocked LLM and mismatched meta phases
    When the meta workflow runs
    Then it raises WorkflowMetaError

  Scenario: worktree isolation removes a clean worktree after the agent
    Given a mocked LLM and a git repository
    When agent runs with worktree isolation and no file changes
    Then the worktree directory is removed

  Scenario: an agent is isolated from prior steps by default
    Given a mocked LLM that echoes the instruction it received
    When a second agent runs after a first without an access list
    Then the second agent's instruction does not contain the first agent's output

  Scenario: an agent can see a designated prior step's output via an access list
    Given a mocked LLM that echoes the instruction it received
    When a second agent runs after a first with the first's label in its access list
    Then the second agent's instruction contains the first agent's output

  Scenario: an agent only sees the steps named in its access list, not others
    Given a mocked LLM that echoes the instruction it received
    When a third agent runs seeing the first but not the second step
    Then the third agent's instruction contains the first agent's output
    And the third agent's instruction does not contain the second agent's output

  Scenario: an access list referencing an unknown step label is ignored
    Given a mocked LLM that echoes the instruction it received
    When an agent runs with an access list naming a step that never ran
    Then it runs and returns its own prompt without error

  Scenario: a schema agent gets the JSON instruction even if a seen step mentions json
    Given a mocked LLM that echoes the instruction it received
    When a schema agent sees a prior step whose output contains the word json
    Then the schema agent's instruction contains the JSON-format directive

