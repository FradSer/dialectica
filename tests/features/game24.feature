Feature: Faithful Tree-of-Thoughts on Game-of-24
  ToT's canonical search benchmark (Yao et al. 2023). Each puzzle is four
  numbers that must combine with + - * / (each used once) to make 24.
  Correctness is ground truth — a Python verifier evaluates the expression
  exactly, no LLM judge — so the experiment can isolate whether faithful ToT
  (partial-state nodes, lookahead value, BFS, winning-leaf output) beats a
  single call on a task that genuinely requires search.

  Scenario: The verifier accepts a correct solution
    Given the puzzle "4 4 6 8"
    When the expression "(4 + 8) * (6 - 4)" is checked
    Then the verification passes

  Scenario: The verifier rejects an expression with the wrong total
    Given the puzzle "4 4 6 8"
    When the expression "4 + 4 + 6 + 8" is checked
    Then the verification fails

  Scenario: The verifier rejects an expression using the wrong numbers
    Given the puzzle "4 4 6 8"
    When the expression "(4 + 8) * (6 - 5)" is checked
    Then the verification fails

  Scenario: The verifier rejects a non-arithmetic expression
    Given the puzzle "4 4 6 8"
    When the expression "__import__('os')" is checked
    Then the verification fails

  Scenario: The expression is extracted from a chain-of-thought answer
    Given a model answer ending in an Answer line
    When the expression is extracted
    Then it is the arithmetic on that line

  Scenario: Faithful ToT solves a puzzle and returns a verifiable winning leaf
    Given an oracle-mocked LLM that proposes legal moves and values reachable states
    When faithful ToT runs on the puzzle "2 4 6 8"
    Then it returns an expression that the verifier accepts
