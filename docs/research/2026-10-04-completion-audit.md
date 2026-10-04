# Research upgrade completion audit

Status: complete. Implementation, all seven frozen studies, final environment/
live verification and fresh independent requirement review are complete. Requirements preserve the full objective
and derive from [the seven-gate acceptance contract](2026-10-03-upgrade.md),
the dependency upgrade request and mandatory real-model/failure-accounting work.

| Requirement | Authoritative evidence | Decision / boundary |
|---|---|---|
| 1. Broad recent primary-source search, counterevidence and reading depth | [32-source literature matrix](2026-10-03-literature.md), including September 30 submissions; relevant methods/limitations inspected for implemented CLR/meta mechanisms and judge follow-up | Complete screening plus selected full-text reading, not 32 full replications; learned/trained policies and infrastructure methods identified separately |
| 2. Honest measurement, pre-event failures, overhead and raw outputs | Runtime ADK callbacks; `tests/test_failed_usage.py`, runtime/journal/measurement regressions; real callback-failure E2E cases; [final frozen integrity audit](results/2026-10-04-heldout-v1/final-integrity-audit.json) | 3,631,216 reported tokens, 3,789 observed turns, 3,072 cached tokens, 30 generation failures retained. Generation/calibration/judging separated; raw prompt/system/output/model/latency retained. Batch unknown0; earlier gateway unknown1 preserved. Workflow steps, ADK turns and opaque provider HTTP/billing are distinct |
| 3. Useful difficulty, independent ground truth, development/held-out separation, coverage vs selection | Separate seed pools, independent portfolio/state verifiers, synthetic evidence tasks, development floor/ceiling diagnostics; [final coverage/selection diagnostics](2026-10-04-heldout-selection-diagnostics.md) and hash-bound derived counts | Held-out Gemini has non-saturated successes/failures; GPT single reaches a declared ceiling. Candidate coverage and final correctness are separate. Claim weighting changes no observed same-candidate correctness; failed claim coverage is missing, not zero. Quote authenticity is not decision correctness |
| 4. Recent mechanisms and applicable controls | CLR claim pattern; typed staged/direct artifact controller pattern; single/consensus/self-refinement; homogeneous/heterogeneous reflection; frozen K=3/K=6 and meta 6/12 studies with exact stored-answer stops and selective context tests | All declared arms/control/budget levels completed. No oracle feedback enters arms; controller/assessment overhead shares outer allowance. Allowances match workflow steps, not actual tokens/USD. Prompted mechanisms are not learned-policy or full paper benchmark replications |
| 5. Real pilots, predeclared repeated held-out comparisons and uncertainty | [Campaign protocol](2026-10-04-heldout-protocol.md), predispatch source archive and child protocols; seven raw/analysis/terminal sets; [complete receipt audit](results/2026-10-04-heldout-v1/complete-receipt-audit.json) | 576 generation trials complete; exact pools, report/protocol/task/config/analysis hashes verified. Objective paired task-cluster bootstrap; evidence unresolved preferences retain bounds. Repeats are not independent task samples; small-pool, unadjusted intervals and judge overlap remain limitations |
| 6. Coherent API, evidence-driven adoption, bilingual docs and migration | English/Chinese README, module docstrings, [runtime migration](2026-10-04-runtime-migration.md), seven result documents and selection diagnostics | Workflow plus verifier-guided repair remains shipped. Claim weighting/controllers did not justify adoption; reflection stays a bounded reference recipe. Strict explicit model configuration and additive observed-turn accounting documented. Final lock/docstring changes occur after frozen experiment, not inside it |
| 7. Regressions, lint/build, fresh review and final real E2E | 212 offline passes; final command logs and [verification receipt](results/2026-10-04-final-verification.json); prior fresh campaign re-review; [final independent completion review](2026-10-04-final-independent-review.md) | All six final checks exit0; 212 offline passed. Gemini/GPT final live E2E: 9 passed, zero skipped, 114.77s. One upstream Pydantic ReadOnly warning. Fresh independent review found no substantive blocker; its stale audit-status observation is resolved |
| Upgrade all dependencies | [Dependency audit](2026-10-04-dependency-audit.md); fresh `uv lock --upgrade` resolves 94 packages; installed ADK 2.11.0, LiteLLM 1.103.2, Pydantic 2.13.5 and zipp 4.1.1 | All available compatible upgrades applied; nine absolute-latest transitive versions conflict with maintained upstream requirements. Frozen environment preserved in archive; final environment separately validated |

## Adoption and measurement boundaries

The two claim budgets establish no adoption-worthy advantage or same-candidate
selection benefit. Staged/direct controllers establish no advantage at either
budget. Self-refinement has favorable point estimates but uncertain gains and
higher realized token costs. Evidence panels show some exploratory positive
signals, not superiority over every roster baseline or human alignment. The
strong single controls reach observed ceilings under two separate contracts;
there are no strong-model mechanism arms, so no such benefit is claimed.

Observable ADK-turn accounting and per-invocation limits resolve the earlier
request-accounting work at the runtime boundary. Hidden SDK/provider retries and
missing billed-token reports cannot be reconstructed. This is explicit scope of
the measurement, not silent zero-cost imputation. The output-token budget is
soft for in-flight calls and excludes input tokens; it is not a hard dollar cap.

Frozen analyses were source/rule-verified before final dependency/docstring edits.
Current source drift does not invalidate those archived experiments or license
rewriting them. Subsequent selection diagnostics are descriptive, hash-bound
post-hoc counts, not a substituted predeclared analysis or held-out tuning.
The final integrity audit rechecks immutable terminal/report/protocol/analysis
bindings and every receipt's record-level usage sums after the campaign.

Final live first attempt is preserved at
`results/2026-10-04-final-live-e2e.txt`: 8 passed, 1 failed because the current
gateway rejected historical Qwen/GLM defaults. No test was skipped or weakened.
The rerun uses the available Gemini/GPT heterogeneous roster via the existing
E2E configuration interface: 9 passed, zero skipped, 114.77s. The saved terminal
output is `results/2026-10-04-final-live-e2e-gemini-gpt.txt`. Both response-before-event
failure scenarios reconcile usage with journals/budgets. One upstream Pydantic
ReadOnly TypedDict warning remains; no unhandled asynchronous task failure was
observed in the passing run.

## Final requirement decision

All seven acceptance gates and the compatible dependency upgrade requirement
have direct evidence above. Final local-reference checks pass; final review found
no substantive blocker. Remaining scientific/runtime limitations are documented
outcomes, not omitted acceptance work: small synthetic task pools, unadjusted
uncertainty, overlapping judge families, strong-single ceilings, incomplete
coverage on failed generations, opaque billing/retries and one upstream Pydantic
warning. No measured superiority or unsupported stable API was manufactured.
