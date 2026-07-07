## Learned User Preferences

- For open-ended reflection and meta-tasks, prefer heterogeneous multi-angle workflows (`reflection_pattern.py`) over AB-MCTS ensembles or LLM-as-scorer ranking.
- Live multi-model evals should route through cliproxy via shell env (`CLIPROXYAPI_HOST`, `CLIPROXYAPI_TOKEN`); `evals/` scripts do not auto-load `dialectica/.env`.
- Set `DIALECTICA_DISABLE_THINKING=true` when running qwen-family models via cliproxy to reduce eval latency.
- Dialectica should mirror Claude Code Workflow orchestration semantics; nested scripts join outer budget via `wf.workflow()`, not isolated `Workflow().run()`.
- When executing attached implementation plans, do not edit the plan file; mark existing todos in_progress instead of recreating them.
- Reflect measured architectural insights into both `README.md` and `README.zh-CN.md` when asked.

## Learned Workspace Facts

- Shipped API is `Workflow` kernel + `create_repair_engine`; demoted engines live in `examples/patterns/` (agentic, dialectic, ensemble, reflection, tot_gan).
- Dialectica thesis: pure-LLM scaffolds tie a prompt-matched single call; measured wins require tools, ground-truth verifiers, or heterogeneous model independence — AB-MCTS float scorer adds no lift over blind heterogeneity.
- `examples/patterns/reflection_pattern.py` (`create_reflection_engine`): Gather → Frame → Critique → Synthesize with per-angle model assignment; default roster `openai:qwen3.6-flash` + `openai:glm-5.2`.
- `evals/reflection_ablation.py` compares hetero vs homo vs single on meta problems; `evals/workflow_ablation.py` is homogeneous reflection vs single.
- `workflow()` is exported from `dialectica.workflow` (not top-level `dialectica`) to avoid submodule name collision; patterns import `from dialectica import workflow as wf`.
- `wf.parallel()` expects a list of thunks, not a bare generator comprehension.
- Cliproxy live eval defaults: `GENERATOR_MODEL_CONFIG=openai:qwen3.6-flash`, `JUDGE_MODEL_CONFIG=openai:qwen3.6-max-preview`, `DIALECTICA_WORKFLOW_CONCURRENCY=4`.
