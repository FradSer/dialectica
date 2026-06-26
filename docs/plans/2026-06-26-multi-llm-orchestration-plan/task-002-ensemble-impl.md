# Task 002 — Ensemble search engine: implementation (Green)

**type:** impl
**depends-on:** ["002-test"]

Implement `EnsembleSearchEngine`, the default Thompson-sampling policy, and
`create_ensemble_engine` so the task-002 suite goes Green. Mirror the
one-engine-per-file thin-wiring style of `repair.py` / `agentic.py`; call the LLM
only through `agent_runtime.run_agent`.

## Files to modify

- `dialectica/ensemble.py` — fill the bodies left as contracts in task 001.
- (No `__init__.py` change — exports already wired in task 001.)

## BDD Scenario

This task makes the full task-002 specification pass. Representative scenario it
must satisfy (full set in `task-002-ensemble-test.md`):

```gherkin
Scenario: A weak candidate from one model is rescued by another going wider
  Given model "alpha" produces a candidate the scorer rates 0.2
  And going deeper on "alpha" cannot exceed 0.3
  And model "beta" produces a candidate the scorer rates 0.85 when sampled wider
  And a max-calls budget of 4
  When the ensemble searches
  Then the winning answer is the one from model "beta"
  And the winning score is at least 0.85
```

## What to implement (what, not how)

1. **Roster construction** — normalize `models` (None → `[get_model_config(
   "GENERATOR")]`); build one `LlmAgent` per config via `create_agent(
   role="Generator", role_name=<distinct stable name>, model_config=cfg)`; wrap
   each as a `ModelArm` with `Beta(1,1)` priors.
2. **FR6 distinctness validation** — at construction, resolve each member's
   effective config; warn loudly (or raise) when two members resolve to the same
   effective model or fall back to default (guards the silent-collapse trap in
   `llm_config._parse_model_config`).
3. **Mandatory scorer** — `scorer` is positional/required; constructing without
   it raises (satisfies "scorer is mandatory").
4. **Search loop** (AB-MCTS-lite, per design `architecture.md`): until
   `best.score >= solved_score` or `calls >= max_calls`:
   - choose action (wider/deeper) and arm via `self.policy` (default: Beta
     Thompson draws; force wider when no candidates yet);
   - WIDER → one `run_agent` call solving fresh (optionally inject the current
     best *failed* answer as an anti-hint); DEEPER → one `run_agent` call
     refining `best.answer` against its score;
   - score the answer with the injected scorer; append a `Candidate`;
   - reward the chosen action-arm and model-arm by how much the new candidate
     improved on the current best score (a bounded, non-negative improvement
     signal; the first candidate counts as a full improvement), updating their
     Beta posteriors; update `best`.
5. **Robustness** — a `run_agent` that raises (non-transient; transient retry is
   already in `run_agent`) is caught and recorded as a failed candidate; the loop
   continues. All-rejected → return best-effort with `passed=False`, never raise.
6. **Return** `{final_answer, passed, attempts, history}` (history entries:
   `{call, action, model, score}`; expose the realized move sequence for the
   schedule assertion). Match repair's contract shape.
7. **Default `Policy`** — implement the Thompson bandit behind the injectable
   seam; seedable (`seed`/injected `random.Random`) for its own determinism;
   round-robin is the documented degenerate fallback.

Interface contracts only were defined in task 001; this task supplies the logic.
No new public surface beyond what task 001 exported.

## Verification

```bash
uv run pytest tests/test_ensemble_feature.py -q   # MUST pass (Green), incl. FR6 unit test
uv run pytest -q                                   # full suite stays green (no regressions)
uv run ruff format --check dialectica/ensemble.py
uv run ruff check dialectica/ensemble.py
```
