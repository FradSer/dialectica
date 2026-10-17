# Embedding reliable workflows

Dialectica provides a Python orchestration kernel and bounded verifier-guided
repair. The host supplies tools, authority, execution isolation and acceptance
checks. This work does not introduce a GUI, a marketplace, automatic general
planning, DeepSeek Harness or coda0 integration.

## Tool authority and workspaces

```python
from pathlib import Path
from dialectica import agent, tool_capability
from dialectica.workflow import worktree_path


@tool_capability(access="read", version="read-source-v1")
def read_source(name: str) -> str:
    root = worktree_path.get()
    if root is None:
        raise RuntimeError("A worktree is required")
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Outside workspace")
    return path.read_text()


# Inside a Workflow script:
# await agent("Inspect the regression", tools=[read_source],
#             agent_type="Explore", isolation="worktree")
```

Explore rejects all unclassified/write tools before constructing an ADK agent,
including wrapped `FunctionTool`s. Apply the declaration to the function before
wrapping. Expandable toolsets and opaque callable objects are rejected in Explore.
Other agent types preserve the existing unrestricted host-supplied tools API.
Tool declarations are trusted host assertions: a read-labelled shell wrapper that
can write is incorrectly configured. The library does not inspect arbitrary
commands, revoke credentials, restrict network access or sandbox Python.

Worktree sessions expose an absolute `worktree_path` ContextVar without calling
`os.chdir`. Host tools must use explicit paths or subprocess `cwd=`. Concurrent
sessions with the same labels have distinct branches. Clean worktrees are removed;
dirty worktrees or status failures preserve the directory. Branch refs remain for
host cleanup. A worktree is Git isolation, not an OS authority boundary. Process
cwd changes elsewhere in the host are outside this contract.

Tool-bearing invocations never automatically restart after transport/tool errors;
schema parse failures in tool-bearing steps also do not re-ask the entire agent.
A single invocation can still request the same tool more than once. The host must
implement idempotency keys, transactions or approvals for consequential tools.

## Versioned resume contract (journal version 2)

Reuse is explicitly enabled with `Workflow(..., resume_version="my-protocol-v1")`.
Without it, pure steps recompute. A host version asserts that relevant closure
state, global configuration, external dependencies and provider revisions have
been represented in `args` or in that version. Bump it when that assertion changes.
Do not depend on mutable hidden globals or a provider alias being immutable.

The cache combines the host version with workflow source/module content, shipped
runtime Python content, Python/ADK/LiteLLM/Pydantic versions, strict JSON args, effective prompt (including resolved
`sees` outputs), schema JSON/content/validators, tool function/module content and
capability version, effective model configuration, instructions and step options.
Registry names do not replace code fingerprints. Opaque/unserializable values or
unavailable source get a fresh nonreusable fingerprint, without `repr` or object ID
fallbacks. A tool capability version must cover dependencies/configuration outside
its source file. A schema's external dependencies are likewise host-versioned.
Versions must also cover code imported by nested workflows from other modules.

Journals use atomic snapshots in `journal.jsonl` (despite the retained filename,
version 2 is one JSON document), OS exclusive run locks and pending intent persisted
before dispatch. The lock releases when a process dies. Concurrent resume of an
active run raises `JournalBusyError`. Old, unknown-version, malformed or truncated
journals are refused; preserve them for inspection and start a new run after
reconciling external effects. Stored journals contain prompts/results and must be
protected by the host. Local journal files are trusted input, not signed evidence.

Only successful text/schema results can be reused. A missing/changed/failed step, rejected cached verification or explicit rerun
invalidates the suffix. Parallel steps reserve invocation positions before yielding;
reordering branches invalidates reuse. No in-flight model request is resumed.
Completed pure steps can be reused after process interruption; non-agent Python
code in the script runs again and must be restart-safe.

All tool/worktree steps are conservatively external, even read tools whose
observations may change. Reusing one requires both `replay_version="artifact-v1"`
and `verify_cached(result)` returning exactly `True` (sync or async). The callback
must check current authoritative evidence, e.g. artifact hash plus a fresh test run.
Exceptions, false or indeterminate checks forbid reuse. A prior external step that
cannot be reconciled raises `ResumeUnsafeError`, including a crash after dispatch
but before a response was journaled. This refusal survives code/input invalidation.
A completed cached result can only be validated when the full fingerprint matches.

After reconciliation the host can explicitly authorize `agent(..., replay="rerun")`
for a restart-safe/idempotent action. This bypasses cached results and can repeat
writes; use a durable host idempotency key, not the agent sequence alone. There is
no general exactly-once guarantee. A pending action needs external reconciliation;
a missing model response cannot establish whether a write happened.

Resume creates a fresh invocation allowance. Cached steps add no new charges;
append-only `usage.jsonl` receipts retain earlier attempts. An interruption can
occur before a receipt is written, so provider billing remains authoritative.
Journals are not a financial ledger and do not guarantee power-loss durability.

## Failure and verification contracts

`parallel` and `pipeline` wait for siblings, then raise `BatchFailed` by default.
Its `outcomes` contain index, completed/failed status, value, error type/message,
traceback, and (for a pipeline) the number of completed stages and last value.
Cancellation propagates after cancelling and settling sibling tasks. `errors="collect"` returns `ItemOutcome` objects;
`errors="legacy"` explicitly selects the previous values/None result shape.
Both modes mark `Workflow.report.status="partial"` when a failure occurred.
Caught agent errors and exhausted schema parsing also mark the run partial.
`Workflow.report` retains execution state, usage, admitted agent steps and errors
when `run()` raises. The journal snapshot records its terminal execution state.
Execution completion does not prove that a domain verifier accepted the result.

Repair accepts a synchronous or asynchronous verifier returning:

```python
from dialectica import VerificationResult

VerificationResult("pass", feedback="", evidence="test command, exit 0, output")
VerificationResult("fail", feedback="assertion failure", evidence="exit 1, traceback")
VerificationResult("indeterminate", feedback="runner unavailable", evidence="timeout")
```

Only `pass` accepts. `fail` supplies feedback for at most `max_attempts` total
candidates. `indeterminate`, checker exceptions and invalid return types stop
without treating the result as accepted. History preserves status, feedback,
evidence and model attribution; `engine.last_history` retains completed verifier
evidence if budget exhaustion or cancellation interrupts a later attempt. Legacy `(bool, str)` tuples remain supported;
truthy strings are not accepted as booleans. The checker owns evidence quality:
substring presence and LLM self-scores are not execution acceptance. Verifier
latency/timeouts, sandboxing, test coverage and resistance to malicious code belong
to the host. The example host uses a fixed test command with a 10-second timeout.

## Budget semantics

- `budget_unit="calls"`: admitted workflow agent steps, including queued steps.
  A tool loop or structured re-ask may contain several model turns.
- `budget_unit="tokens"`: reported output tokens including reported thinking.
  Queued dispatch and re-asks check again; already in-flight calls may overshoot.
  Unknown usage blocks later admission, rather than assuming zero cost.
- `model_turn_limit=N`: a separate shared cap on ADK before-model admissions
  across steps, branches and nested workflows. Counts tool loops, transport retries
  and cache short circuits; excludes hidden SDK/provider-internal retries.
- `usage().model_calls`: observed model turns, distinct from admitted agent steps.
  `unknown_calls` marks missing final usage. A mocked plain string marks an unknown
  invocation without inventing an observed turn. Prompt/output/total/cache counts
  are recorded separately, including failed-attempt reports.

No option is a dollar hard limit. Use provider quotas for financial enforcement.
Cancellation cannot forcibly stop a synchronous tool already running in a thread.

## Minimal repair scenario and matched comparison

```bash
uv sync --frozen
uv run python -m evals.workflow_bugfix_eval --output /tmp/dialectica-bugs
# Select one scenario, with the same failed test -> diagnosis -> patch -> tests:
uv run python -m evals.workflow_bugfix_eval --fixture binary-search-edge \
  --output /tmp/dialectica-one-bug
```

The host in `examples/bugfix_workflow.py` supplies read/edit/test tools; the core
library does not rebuild a tool platform. Each arm gets a fresh directory,
`target.py`, the same visible tests and the initial failure. Outputs include
`patch.diff`, `tests.json` (commands/exit codes/stdout/stderr), `result.json` and a
paired `summary.json`. Final acceptance requires initial failure, a nonempty patch,
passing final tests and completed execution. One bounded additional patch step is
allowed when the structured workflow's external test fails.

The ten cases are **authored fixtures**, covering range endpoints, mutable defaults,
empty inputs, zero settings, Unicode normalization, numeric sorting, file suffixes,
century leap years, dictionary mutation and binary-search edges. They are not ten
historical bugs and are too small to support broad performance claims. The real
repository regressions were first demonstrated failing on main `19c9f98`; see the
[validation record](workflow-reliability-validation.md).

Default execution uses a reference-patch adapter: offline smoke tests verify
orchestration/evidence only. There are no model calls or measured quality gains;
usage and cost are `null`, not zero-cost model estimates. Repeated independent
live runs and a more representative historical dataset are still required.

A live run requires explicit opt-in and existing host credentials:

```bash
# Choose a provider model and immutable revision supported by your own account.
uv run python -m evals.workflow_bugfix_eval --live \
  --model 'provider:model' --model-version 'provider-revision' \
  --turn-limit 12 --timeout 120 --output /tmp/dialectica-live
```

Both arms use the same model configuration, requested version, tools,
6-step allowance, shared 12-model-turn admission cap, timeout and test feedback.
The single agent may self-repair freely in its tool loop; it is not a single
unchecked model completion. The workflow uses diagnosis/patch/optional repair.
Controller overhead counts toward the same allowance. Arm order is paired and
seed-randomized. Usage is taken from actual runtime reports, never estimated from
step counts. Results record completion, automatic-run human intervention count,
wall time and missing usage; `cost_usd` remains unknown without provider billing
receipts. Attach billing evidence before comparing financial cost. Model-version
metadata is a host-supplied identifier; pin and audit actual provider revisions.
The harness does not create credentials or call a paid provider by default.

The narrow path checks and temporary directories in the example are **not a code
sandbox**. Live generated Python executes with host authority. Use a host-supplied
container/OS sandbox for untrusted models or code before enabling live execution.
