# Best Practices & Pitfalls

Vocabulary is canonical per `_index.md` Glossary: **roster / arm / scorer /
verifier / wider / deeper / policy / candidate**.

## The honesty trap (the one that matters most)

This repo's hard-won finding (`CLAUDE.md`, `repair.py:1-18`) is that a pure-LLM
scaffold only rearranges one model's thinking and **ties a prompt-matched single
call**. An ensemble that ranks with a *fake* signal (length, recency, random) is
exactly such a scaffold dressed up in N models.

Two layers of defence, both required:

1. **Structural** — the scorer is a **mandatory positional constructor arg**; the
   engine refuses to construct without one. Pure-scaffold misuse is
   unrepresentable (BDD "scorer is mandatory").
2. **Empirical** — the `evals/ensemble_ablation.py` honesty gate **must** include
   the **blind-pick control** (arm (c): same N heterogeneous candidates, signal
   replaced by random) at matched call cost, alongside best-of-N on the strongest
   single model (arm (b)). KEEP only if (a) > (b) AND (a) > (c). This is the
   SWE-suite lesson made procedure: a lift that dissolves under a matched-cost
   resampling control was resampling luck, not the mechanism.

Never let an LLM-judge become the engine's default signal — same-model
self-scoring was measured to add nothing. If a caller injects an LLM-judge
scorer, that is their signal to own and validate.

## Determinism & seeding

- **Never call un-seeded `random` in the search loop.** (The jitter in
  `agent_runtime.py` backoff is fine; a non-reproducible *schedule* is not.)
- The wider-vs-deeper + arm decision lives behind an **injectable policy**. Tests
  inject a scripted deterministic policy; the default Thompson bandit takes a
  `seed` (or an injected `random.Random`) for its own focused unit test.
- **Expose the realized move trace** (`history` / `result["moves"]`) so behavioral
  tests assert on a returned value, not on log scraping.

## Cost & concurrency

- **Reuse `DIALECTICA_MAX_CONCURRENCY`** — do not invent a new limiter. The global
  semaphore in `agent_runtime.py:36-43` already caps overlapping calls and is what
  `parallel`/`pipeline` honor; route any fan-out through `run_agent` to share it.
  Tests set/reset it via `agent_runtime._reset_concurrency_limiter`
  (`agent_runtime.py:29`).
- AB-MCTS is mostly **sequential** (each decision needs the prior score), so
  contention is low; this is a feature, not a limitation, for an adaptive loop.
- **Rate-limit handling already exists** — `run_agent` has a separate retry budget
  + jittered cooldown for 429/RESOURCE_EXHAUSTED (`agent_runtime.py:62-123`). Do
  not duplicate it. The "a model raises → failed candidate" path is for
  *non-transient* failures: let `run_agent`'s retry exhaust first, then catch and
  record the failed candidate (test with a plain `RuntimeError`, not a rate-limit
  string, so it surfaces immediately).
- **Matched-cost is ambiguous across providers** — a call to a 30B model ≠ a call
  to a flash model. Define the primary budget in **LLM-call count** (matching the
  existing ablations) and document token/$ asymmetry as a caveat; a
  token-normalized secondary view is optional.

## Avoid silent model-fallback masking a misconfig

`llm_config._parse_model_config` silently falls back to `gemini-3.5-flash` when a
provider key is missing (`dialectica/llm_config.py:53-79`). A "heterogeneous"
roster whose members all collapse to the same default is the worst failure mode —
it *looks* like an ensemble but is N copies of one model, guaranteeing the
honesty trap. **Validate roster distinctness at construction (FR6)**: resolve each
member's effective config; warn loudly or error if two resolve to the same model
or fell back to default. Test this as a focused unit test against the real
`llm_config` (the mocked seam hides the fallback).

## Back-compat is a contract, not a nicety

- The existing repair scenarios (`tests/features/repair.feature:6-23`) and
  `create_repair_engine`'s current signature (`repair.py:119`) must stay green.
- Add the roster via an **optional** `models` parameter; when `None`, behavior is
  byte-for-byte the existing single-agent path. The "single-model unchanged"
  scenario locks this.
- `model_config` + `models` together → `ValueError` (don't silently pick one).

## Multi-model repair must not hide which model fixed it

Record the producing model per attempt in `history` (FR10). This is both a
debuggability requirement and the evidence that the *roster* (not luck) did the
work — without it you cannot distinguish a real cross-model rescue from resampling
the same model. It is what the repair sub-criterion ablation reads.

## Testing strategy (offline, deterministic, single-seam)

- **Fake heterogeneous models at the one seam**, dispatching on `agent.name` (each
  arm has a distinct stable name; `agent.model` is a bare string only for the
  `google` provider — a `LiteLlm` object otherwise). Per-model canned outputs as a
  dict/list (list = consumed in order, so wider vs deeper can differ); a `RAISE`
  sentinel for the model-raises path. Generalize the existing fakes in
  `tests/helpers.py` (which already branch on `agent.name`).
- **Scorer / verifier / policy are pure Python closures** built in the step — no
  LLM, fully deterministic (mirrors `tests/test_repair_feature.py:30-31`).
- **Count calls per model** with a `collections.Counter` in the fake; assert total
  (budget) and per-model (rescue, back-compat) counts.
- **Keep schema re-ask out of these tests** — the ensemble generates raw text
  scored by the injected scorer, not `output_schema` JSON. The schema-parse/re-ask
  machinery (`workflow.py:256-294`, tested at `tests/test_workflow_feature.py:205`)
  is a separate seam; don't entangle bandit-schedule assertions with JSON-parse
  flakiness.
- **No API key needed** — `conftest.py` only loads `.env` for the e2e skip guard;
  mocked tests never hit the network. `@when` wraps `asyncio.run(engine.run())`.

## Code quality

- Mirror the one-engine-per-file thin-wiring style of `repair.py` / `agentic.py`;
  no god-engine, no premature abstraction (2-3 models is the scale — `if`/rotation,
  not a plugin framework).
- 3.11+ type hints, `@dataclass` for engine-internal value objects, async
  throughout. No casts to `any`, no defensive try/except in trusted codepaths
  (let `run_agent` own transport resilience).
- Cross-reference the ensemble and repair docstrings so their relationship
  (adaptive float-scorer search vs deeper-only boolean-verifier rotation) is
  explicit.

## Security / safety

- No code self-modification, no `eval`/`exec` of model output in the engine — the
  scorer/verifier is caller-supplied and the caller owns any sandboxing of code
  execution (same posture as `repair.py`).
- The engine adds no new credential handling; provider keys are read by the
  existing `llm_config` path. Do not log full prompts/answers at info level
  (`run_agent` already logs at warning for failures only).
