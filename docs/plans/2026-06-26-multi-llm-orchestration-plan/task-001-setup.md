# Task 001 — Setup: ensemble module contracts, exports, test fake

**type:** setup
**depends-on:** []

Foundation task. Creates the contract surface (signatures only, **no bodies**)
so the Red test tasks (002, 004) can import the symbols, plus the shared
heterogeneous-model test fake both feature pairs need.

## Why this is foundation

Both feature pairs import from `dialectica.ensemble` (002/003) and rely on a
per-model dispatch fake (002 and 004). Defining the contracts and the fake once,
first, unblocks both pairs to proceed in parallel.

## Files to create / modify

- `dialectica/ensemble.py` (new) — contracts only, no logic:
  - `Scorer = Callable[[str], float]` type alias.
  - `Policy` interface (Protocol or small ABC) with `choose_action(...)` and
    `choose_arm(...)` signatures — the injectable wider/deeper + arm seam.
  - `@dataclass ModelArm` (`config`, `agent`, `name`, `alpha=1.0`, `beta=1.0`).
  - `@dataclass Candidate` (`answer`, `score`, `model`, `action`, `depth`,
    `parent`).
  - `class EnsembleSearchEngine` with `__init__(self, problem, scorer, roster,
    max_calls=8, solved_score=1.0, solution_format="", policy=None)` and
    `async def run(self) -> dict[str, Any]: ...` (signatures only; `run` may
    `raise NotImplementedError`).
  - `def create_ensemble_engine(problem, scorer, models=None, max_calls=8,
    solved_score=1.0, solution_format="", policy=None) -> EnsembleSearchEngine:`
    (signature only).
- `dialectica/__init__.py` — add `from .ensemble import (EnsembleSearchEngine,
  create_ensemble_engine)`; add both to `__all__` in the engine block; add a
  one-line entry to the module-docstring hierarchy positioning the ensemble as a
  *capability-adding* engine (ground-truth scorer = information a single pass
  lacks); bump `__version__` (0.5.0 → 0.6.0).
- `tests/helpers.py` — add a heterogeneous-model fake builder that patches the
  single seam `agent_runtime.run_agent`, **dispatches on `agent.name`** (each
  roster arm gets a distinct stable name, e.g. `Candidate[alpha]`), supports
  per-model canned outputs (a string, or a list consumed in order so wider vs
  deeper can differ) and a `RAISE` sentinel, and counts calls per model
  (`collections.Counter`). Signature only + docstring is acceptable here if the
  body is trivial wiring; a small body is allowed since this is a test helper,
  not production logic.

## BDD Scenario

This setup task is not itself driven by a single scenario; it enables the
scenarios in tasks 002 and 004. No Gherkin body. (Foundation/setup tasks are
the documented exception to the one-scenario-per-task rule.)

## Steps (what, not how)

1. Create `dialectica/ensemble.py` with the type alias, `Policy` interface, the
   two dataclasses, and the engine/factory **signatures** — no algorithm bodies.
   Cross-reference repair's `Verifier` in the module docstring (scorer ranks via
   float; verifier gates via bool+feedback).
2. Wire `__init__.py` exports, `__all__`, docstring hierarchy line, and version
   bump.
3. Add the heterogeneous-model fake to `tests/helpers.py` (dispatch on
   `agent.name`, per-model canned outputs, `RAISE` sentinel, per-model call
   counter).

## Verification

```bash
uv run python -c "from dialectica import EnsembleSearchEngine, create_ensemble_engine; print('imports ok')"
uv run python -c "from tests.helpers import *; print('helper import ok')"
uv run ruff format --check dialectica/ensemble.py dialectica/__init__.py
uv run ruff check dialectica/ensemble.py dialectica/__init__.py
```

All four must succeed. (The engine `run()` is not exercised yet — only that the
contracts import and lint.)
