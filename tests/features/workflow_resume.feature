Feature: Workflow resume and journaling
  Each agent() call is journaled by sequence and cache key. Resuming with the
  same script and args replays the longest unchanged prefix from cache without
  calling the LLM again.

  Scenario: A run journals each agent call
    Given a mocked LLM
    When a workflow runs two agent calls
    Then the journal records 2 entries

  Scenario: Resume with the same script and args hits the journal cache
    Given a mocked LLM that counts calls
    When the same workflow is resumed with the prior run id
    Then no LLM calls were made on resume

  Scenario: Resume with different args bypasses the journal cache
    Given a mocked LLM that counts calls
    When the workflow resumes with different args
    Then the LLM was called again on resume

  Scenario: run_id is readable during a workflow run
    Given a mocked LLM
    When a workflow script reads run_id
    Then the run id is a non-empty string
