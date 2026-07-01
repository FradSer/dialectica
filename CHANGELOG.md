# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.7.0]

### BREAKING

- `create_agentic_engine`, `create_ensemble_engine`, `create_dialectic_engine`,
  `create_engine`/`create_coordinator` and their supporting `Protocol`/model
  types (`Generator`, `Evaluator`, `Selector`, `Synthesizer`,
  `DiscriminatorVerdict`, `EvaluationResult`, `ThoughtData`) are removed from
  the public API (`dialectica.__all__`). Each was measured (see README
  "Evaluation") to either need nothing beyond `agent(tools=...)` (agentic) or
  to tie/lose a prompt-matched single call / be CUT by the honesty gate
  (ensemble, dialectic, ToT+GAN). They remain available as unshipped
  reference implementations in `examples/patterns/` (not installed via
  `pip install dialectica`) with identical factory names, signatures, and
  return shapes — see README "Migration from 0.6.x".
- `dialectica.gan_evaluator` is renamed `dialectica.json_repair`. Only the
  shared `strip_code_fence`/`repair_json_escapes` helpers survive;
  `AdversarialEvaluator`, `SinglePassEvaluator`, `score_thought`, and the
  discriminator circuit breaker moved to `examples/patterns/tot_gan_pattern.py`
  (the circuit breaker itself was not ported).
- `IterativeRepairEngine`'s constructor now takes resolved model-config
  strings instead of `LlmAgent` objects (an internal rebuild onto the
  `Workflow` kernel). `create_repair_engine()`'s factory signature and return
  shape are unchanged.
- `agent_factory.ROLE_TEMPLATES` is trimmed to `{"Generator": ...}` only.

### Added

- `workflow.agent()` gains `instructions: str` — appends task-specific
  system-prompt framing (the same role `agentic_pattern.py`'s system prompt
  plays), letting a workflow stage act like the (now-demoted) Agentic engine
  without a dedicated class.
- `examples/patterns/` — runnable reference implementations of the demoted
  engines (`agentic_pattern.py`, `dialectic_pattern.py`, `ensemble_pattern.py`,
  `tot_gan_pattern.py`), each rebuilt on the `Workflow` kernel. Not shipped in
  the wheel (dev tool, like `evals/`).
- `tests/test_example_patterns_smoke.py` — one mocked end-to-end smoke test
  per demoted pattern.

### Fixed

- `workflow.agent(model=...)` now resolves `"provider:model"` strings through
  `llm_config._parse_model_config` before building the underlying agent.
  Previously the raw string was passed straight through, so a non-Google
  `model=` override was never wrapped in `LiteLlm` and never actually routed
  to that provider — a latent bug never caught because no test or eval had
  called `wf.agent(model=...)` before this release's `create_repair_engine`
  rebuild exercised it.
- Fixed a pre-existing version drift between `pyproject.toml` (`0.5.0`) and
  `dialectica.__version__` (`0.6.0`) — both now read `0.7.0`.
- `examples/patterns/_scoring.Verdict` regained the `flaws`/`suggestions`
  object-to-string coercion the deleted `DiscriminatorVerdict` had (found by
  independent audit): some backends return flaw/suggestion entries as objects
  (e.g. `{"category": ..., "text": ...}`), which failed `list[str]` validation
  and silently scored 0.0 on every retry without it. Affects
  `dialectic_pattern.py` and `tot_gan_pattern.py`.
- `agent_factory.ROLE_TEMPLATES["Generator"]` now puts `{additional_context}`
  last instead of sandwiching it before a fixed "Generate thoughts that
  advance the problem-solving process" closing line (found by independent
  audit): `agentic_pattern.py`'s injected "act, don't guess — use tools"
  framing was being followed by that generic closing line, directly
  contradicting it. Default (no-`instructions`) callers are unaffected in
  substance — same content, `additional_context` just moved to the end and
  trailing whitespace is now stripped.
- `llm_config._parse_model_config` docstring now documents that a bare model
  name (no `provider:` prefix) silently falls back to the default model with
  no warning logged, unlike every other fallback path in that function.

See README "Migration from 0.6.x" for upgrade guidance.
