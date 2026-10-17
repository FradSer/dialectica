# Workflow reliability validation — 2026-10-17

Base: `main` at `19c9f98e4382aebafe7786ce7074780bbb3c5da3`.
Implementation used an independent clone on Mac.lan, with no pre-existing local
changes in that clone and no open PR at initial inspection. No other checkout was
modified. No model credentials were created and no live model evaluations ran.

## Baseline evidence

The first three regression tests were run before changing library code; all failed:

- Concurrent worktree sessions changed the process cwd across awaits.
- Explore accepted an unclassified write tool.
- Different schemas with the same class name generated the same cache key.

See [captured failure summary](evidence/workflow-reliability/baseline-regressions.txt).
Additional baseline execution recorded a partial batch returning `null` for its
failed member, a 10-output-token budget dispatching two queued steps and reporting
20 tokens even at concurrency 1, a verifier returning the string `"yes"` being
accepted, changed script code retaining its fingerprint, and equivalent tool
instances receiving different keys. See the [raw behavior record](evidence/workflow-reliability/baseline-behavior.json).

To reproduce those baseline behaviors with the locked development interpreter:

```bash
mkdir /tmp/dialectica-baseline-check
 git archive 19c9f98 | tar -x -C /tmp/dialectica-baseline-check
cp docs/evidence/workflow-reliability/reproduce_baseline.py /tmp/dialectica-baseline-check/
.venv/bin/python /tmp/dialectica-baseline-check/reproduce_baseline.py
```

The baseline script deliberately exercises old behavior and is not a workflow
recipe. Current APIs reject or expose these conditions instead.

## Local verification

macOS arm64 on Mac.lan, Python 3.11.13, dependencies installed with `uv sync --frozen`.
The project has no pre-existing typecheck command; a temporary Pyright 1.1.414
installation was used without changing runtime/development dependencies.

| Check | Result |
| --- | --- |
| `.venv/bin/pytest -q` | **276 passed, 9 deselected** |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check .` | Passed |
| `uvx pyright --pythonpath .venv/bin/python dialectica evals/workflow_bug_fixtures.py evals/workflow_bugfix_eval.py examples/bugfix_workflow.py` | **0 errors, 0 warnings** |
| `python -m compileall -q dialectica` plus new eval/example modules | Passed |
| `uv build --offline --out-dir /tmp/dialectica-dist` | Source distribution and wheel built |
| `git diff --check` | Passed |

The 9 deselected tests are opt-in live `e2e` / `e2e_access` tests, excluded by the
repository's normal pytest configuration. They were not reported as passing.

Reliability regressions include cross-process fingerprint stability, code/input/
schema invalidation, explicit reuse opt-in, rejected verification invalidating the
tail, versioned tool-result revalidation, unknown-usage admission refusal, queued
token admission, a real ADK tool loop hitting the shared model-turn cap, and real
concurrent ADK worktree tools both on and off the thread pool. Cancellation settles
siblings before the run ends. A real process exits mid-run; its completed pure
prefix is reused, while an uncertain external write is refused on resume and is
not repeated. Exclusive resume locks, damaged/legacy journal refusal and repair
history surviving budget exhaustion are also tested.

## Offline repair evidence

```bash
.venv/bin/python -m evals.workflow_bugfix_eval --output /tmp/dialectica-bugfix-final
```

All ten authored fixtures started with failing executable tests and ended with a
passing reference patch in both arms (**20/20 plumbing runs**). This is an offline
smoke result, not model performance. Each fixture is explicitly marked as authored,
not a historical repository bug. The adapter sees known reference fixes; a live
agent does not receive that source module or reference patch in its workspace.

The [recorded summary](evidence/workflow-reliability/offline-smoke.json) retains
completion, interventions, elapsed time, fixture/lockfile/patch hashes, allowances
and unknown usage/cost. No dollar comparison is justified. A concrete example is
the [one-line binary-search patch](evidence/workflow-reliability/binary-search.patch)
and [test execution evidence](evidence/workflow-reliability/binary-search-tests.json).
Executable/workspace prefixes in the latter are normalized and labelled; assertion
output and exit codes are unchanged.

Remaining evaluation work: run paired, repeated live trials with an approved
provider budget, pin/audit actual model revisions, attach provider billing receipts,
and replace/augment the small fixtures with representative historical bugs.
Windows locking has an implementation path but was not exercised on this host.
A host-provided OS/container sandbox is still needed for untrusted live code.

## Independent code review after incomplete external coverage

An independent reviewer agent audited PR #10 against base `19c9f98` without
editing the implementation or invoking live models. The reviewed initial head was
`6e19443`. Two new-contract defects and one existing compatibility omission were
reproduced with offline calls:

| Finding | Reproduction and fix |
| --- | --- |
| P1: asynchronous cached verification could reuse an invalidated parallel suffix | First step rejected its cache while a later verifier accepted; resume returned `first-fresh, tail-old`. Concurrent verifiers now wait for all earlier cache decisions and recheck validity before returning. Live execution stays outside the decision barrier. |
| P2: caught preflight refusals could report completed | Caught budget, Explore permission and unsafe-resume refusals now retain typed errors/tracebacks and mark a normally returning script partial. One public boundary records failures, including execution and persistence errors. |
| P2: cached agent skipped phase registration (also present on base) | A declared agent phase now registers on cached return, so resumed meta validation matches initial execution. |

The six direct parametrized regressions failed before these fixes and passed
following them. Three additional regressions cover refusal of an invalidated
external suffix without repeating its effects, cancellation releasing decision
waiters, and refusal of workflow-agent reentry from a verifier without deadlock.
The same reviewer independently reran the original reproducer and all nine new
regressions after the fixes, confirmed the public signature/coroutine behavior,
and reported no remaining blocking findings.
See `tests/test_independent_review_regressions.py`. A verifier uses host checks
directly; it cannot invoke workflow agents and create circular decision waits.

This is independent agent code review and offline regression evidence, not a
completed external service review. Devin skipped substantive review because its
trial expired with no credits. Code Terrier's latest completed review on the
previous head was neutral: exploration budget reached, full coverage unavailable.
Neither service result establishes a clean code review. No reviewer quota,
billing or configuration was changed, and the PR was not split or merged.
