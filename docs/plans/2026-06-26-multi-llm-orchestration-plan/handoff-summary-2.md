# Handoff Summary — Batch 2 (multi-model repair)

**Status:** COMPLETE. Task 003-test + 003-impl done.

**Delivered:**
- `dialectica/repair.py` — `IterativeRepairEngine` accepts a single agent or a
  roster (normalized to a list), rotates round-robin per attempt, records
  `history[i]["model"]`. `create_repair_engine` gains `models: list[str] | None`
  (mutually exclusive with `model_config` → `ValueError`).
- `tests/features/repair.feature` — 4 scenarios appended (original 3 untouched).
- `tests/test_repair_feature.py` — roster step defs reusing the Batch-1 fake.

**Orchestrator fix applied after coordinator handoff (latent bug):** the
coordinator used the raw config as the agent `role_name`, which ADK rejects for
real configs containing `:`/`.`/`-` (tests passed only because they use bare
labels `"A"/"B"`). Fixed by sanitizing agent names (`_safe_agent_name`) while
recording the **raw config** as the history label via a new `model_labels`
param on `IterativeRepairEngine`. Verified: real configs
`["google:gemini-3.5-flash", "openrouter:qwen3.6-32b"]` now construct, and
`history` records the raw configs (needed by the Batch-3 ablation).

**Verification (independently re-run):** 7/7 repair tests, 133 full suite, ruff
clean. Back-compat single-model path preserved.

**For Batch 3:** `history[i]["model"]` carries the raw `provider:model` config —
the ablation can attribute repair fixes to model-switching by comparing these.
