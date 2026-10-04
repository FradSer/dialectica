# Runtime migration and research boundaries

This describes implemented runtime behavior. The seven repeated held-out studies are complete. Their evidence does not
justify promoting claim/controller mechanisms to stable API; see
[the completion audit](2026-10-04-completion-audit.md) for final verification.

## Model resolution

Explicit model settings must be nonempty `provider:model` values. Invalid or
unsupported settings now raise before dispatch rather than silently falling back
to Gemini. Remove an environment override to select the native default; an empty
override is an error. Role-specific settings take precedence over the default.
OpenAI-compatible routes require both `OPENAI_API_BASE` and `OPENAI_API_KEY`;
OpenRouter requires `OPENROUTER_API_KEY` and retains its provider route. Never
include credentials in model names or experiment reports. Applications remain
responsible for environment loading; the library does not load `.env`.

## Usage and failures

`TokenUsage.model_calls` is an additive field counting observable ADK model turns,
including runtime retries, tool loops and cache short circuits. It is different
from `spent_calls()`, which counts workflow agent steps. Neither measures opaque
SDK/provider HTTP retries or exact billed request counts.

ADK callbacks capture reported usage before events are returned. Usage from failed
attempts accumulates into successful retries or the final exception's
`dialectica_usage`. The workflow budget and journal retain failed-step usage;
failed steps are not replayed as successful answers. Cancellation preserves prior
reported usage. Partial reports are retained until a final cumulative report
replaces them, preventing duplicate accumulation.

`unknown_calls>0` means at least one attempt lacks a final usage report. Recorded
tokens are then an incomplete cost observation. A gateway failure without token
metadata cannot be reconstructed as a precise token amount: record the attempt
and unknown usage, rather than claiming it was free. Old journals without
`model_calls` remain readable; their default zero means the field was unrecorded.

`budget_unit="tokens"` limits reported output tokens, including reported thinking
tokens. It does not limit input or total tokens. An in-flight call can overshoot;
the next entry is rejected once the recorded budget is exhausted. Concurrent
in-flight calls and unknown usage prevent interpreting this as a hard dollar cap.
Nested patterns must join `wf.workflow()` to share the outer budget.

## ADK runtime options

`DIALECTICA_MAX_LLM_CALLS` bounds ADK turns within one invocation and must be a
positive integer. When absent, ADK reads its native limit. Reaching the limit
fails rather than restarting the tool loop. This is separate from the workflow's
step or output-token allowance.

`DIALECTICA_TOOL_WORKERS` opts synchronous tools into ADK's thread pool. Tools
requiring the calling thread should leave it unset. Python cannot forcibly stop
an already executing synchronous thread. Context caching is opt-in and applies
within a tool loop; separate workflow steps do not automatically share a cache.
Telemetry is opt-in through the documented ADK/OpenTelemetry environment settings.

## Public surface and experiments

The shipped surface remains the Workflow kernel and verifier-guided repair.
Claim falsification and staged/direct meta-reasoning stay in `examples/patterns/`;
their execution tests do not establish quality gains. Objective comparisons keep
the oracle in the evaluator. Open-ended quotation checks establish authentic
quotes, not decision correctness, and panel agreement does not establish human
alignment. Invalid measurements and disagreements remain visible.

The completed campaign froze source, dependencies, tasks, configuration and
analysis rules before dispatch. All report/protocol/analysis hashes and usage
sums were verified against those inputs before final edits. The source archive
preserves that environment; final zipp/docstring changes are subsequent changes,
not retroactively part of the experiment. The
[held-out protocol](2026-10-04-heldout-protocol.md) specifies comparisons;
[the dependency audit](2026-10-04-dependency-audit.md) records the final compatible
upgrade. Descriptive [selection diagnostics](2026-10-04-heldout-selection-diagnostics.md)
retain missing failure coverage and do not retune the mechanisms.
