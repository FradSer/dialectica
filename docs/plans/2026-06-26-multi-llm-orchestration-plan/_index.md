# Plan: Heterogeneous Multi-LLM Orchestration

Implementation plan for the design at
`docs/plans/2026-06-26-multi-llm-orchestration-design/` (evaluator PASS,
commit `e47d6a8`). Vocabulary is canonical per the design Glossary:
**roster / arm / scorer / verifier / wider / deeper / policy / candidate /
EnsembleSearchEngine**.

## Context

Dialectica's thesis: no pure-LLM scaffold beats a prompt-matched single call on
self-contained tasks; engines win only by adding information a single pass lacks
(tools, ground-truth verification, scale, independence). A two-pass review of
Sakana AI's portfolio confirmed the same law and identified exactly two
transferable, inference-time, API-level mechanisms: heterogeneous-model search
ranked by a ground-truth signal, and verifier-gated multi-model repair. This
plan implements both as focused engines on the existing single LLM seam
(`agent_runtime.run_agent`), each guarded so it can never degrade into a pure
scaffold (the selection signal is a mandatory constructor arg), and ships the
non-negotiable three-arm honesty-gate eval that decides KEEP vs CUT.

### Current state vs target state

| Dimension | Current | Target |
|---|---|---|
| Model count per engine | One `model_config` per role/engine (single family) | A **roster** of N heterogeneous `provider:model` configs as bandit arms |
| Engines | `agentic`, `repair`, `dialectic`, legacy ToT | + `EnsembleSearchEngine` (AB-MCTS-lite); `repair` gains optional multi-model rotation |
| Selection signal | repair's injected `verifier` (bool+feedback) | + ensemble's injected `scorer` (float); both mandatory |
| repair API | single generator | optional `models` roster, rotation on failure, per-attempt model in `history` (back-compatible) |
| Honesty measurement | `repair_ablation`, `workflow_ablation` | + `evals/ensemble_ablation.py` (3-arm: ensemble+signal / best-single best-of-N / ensemble blind-pick) |
| Public API | no ensemble export | `create_ensemble_engine` / `EnsembleSearchEngine` in `__all__`; version bump |

## Execution Plan

Test/impl pairs share an `NNN` prefix and slug (per the plan checklist's
filename-pairing rule); the YAML `id` carries the type suffix to stay unique, and
each task lists its `file` explicitly so `depends-on` is unambiguous.

```yaml
tasks:
  - id: "001"
    subject: "Scaffold ensemble module contracts, exports, and heterogeneous-model test fake"
    slug: "setup"
    type: "setup"
    file: "task-001-setup.md"
    depends-on: []
  - id: "002-test"
    subject: "Ensemble search engine — BDD scenarios (Red)"
    slug: "ensemble"
    type: "test"
    file: "task-002-ensemble-test.md"
    depends-on: ["001"]
  - id: "002-impl"
    subject: "Ensemble search engine — implementation (Green)"
    slug: "ensemble"
    type: "impl"
    file: "task-002-ensemble-impl.md"
    depends-on: ["002-test"]
  - id: "003-test"
    subject: "Multi-model repair — BDD scenarios (Red)"
    slug: "repair-multimodel"
    type: "test"
    file: "task-003-repair-multimodel-test.md"
    depends-on: ["001"]
  - id: "003-impl"
    subject: "Multi-model repair — implementation (Green)"
    slug: "repair-multimodel"
    type: "impl"
    file: "task-003-repair-multimodel-impl.md"
    depends-on: ["003-test"]
  - id: "004"
    subject: "Honesty-gate ablation harness (3-arm + repair sub-criterion)"
    slug: "ensemble-ablation"
    type: "eval"
    file: "task-004-ensemble-ablation.md"
    depends-on: ["002-impl", "003-impl"]
```

## Task File References

- [Task 001: Setup](./task-001-setup.md)
- [Task 002: Ensemble Test (Red)](./task-002-ensemble-test.md)
- [Task 002: Ensemble Impl (Green)](./task-002-ensemble-impl.md)
- [Task 003: Multi-model Repair Test (Red)](./task-003-repair-multimodel-test.md)
- [Task 003: Multi-model Repair Impl (Green)](./task-003-repair-multimodel-impl.md)
- [Task 004: Honesty-gate Ablation Harness](./task-004-ensemble-ablation.md)

## BDD Coverage

All 12 design scenarios + the FR6 roster-distinctness unit test are mapped:

| Scenario (from design `bdd-specs.md`) | Test task | Impl task |
|---|---|---|
| The highest-scoring candidate across models wins | 002-test | 002-impl |
| The schedule alternates wider and deeper under an injected policy | 002-test | 002-impl |
| A weak candidate from one model is rescued by another going wider | 002-test | 002-impl |
| The scorer is mandatory | 002-test | 002-impl |
| Search stops at the max-calls budget and returns best-so-far | 002-test | 002-impl |
| Solved score short-circuits before the budget is spent | 002-test | 002-impl |
| Every candidate is rejected — best-effort is returned, not an error | 002-test | 002-impl |
| A model that raises is treated as a failed candidate, not a crash | 002-test | 002-impl |
| FR6 roster-distinctness (unit test, real `llm_config`) | 002-test | 002-impl |
| A roster switches model after a verifier failure | 003-test | 003-impl |
| Single-model repair is unchanged when no roster is given | 003-test | 003-impl |
| The roster cycles back when failures exceed the roster size | 003-test | 003-impl |
| Passing model_config and models together is rejected | 003-test | 003-impl |
| Honesty gate (success criteria, no Gherkin — dev harness) | — | 004 |

## Dependency Chain

Verified acyclic by the Phase 4 dependency-graph sub-agent. Two independent
Red→Green branches fan out from the foundation and join at the eval harness:

```
                  ┌─> 002-test ──────> 002-impl ───────┐
                  │   (ensemble Red)   (ensemble Green) │
 001 setup ───────┤                                     ├──> 004 ablation
 (foundation)     │                                     │      (eval harness)
                  └─> 003-test ──────> 003-impl ────────┘
                      (repair Red)     (repair Green)

 Edges (A ──> B means "B depends-on A"):
   001 -> 002-test    002-test -> 002-impl    002-impl -> 004
   001 -> 003-test    003-test -> 003-impl    003-impl -> 004
```

Parallelism: after 001, the ensemble branch `{002-test → 002-impl}` runs fully in
parallel with the repair branch `{003-test → 003-impl}` (disjoint files:
`ensemble.py`/`ensemble.feature` vs `repair.py`/`repair.feature`). Task 004 is the
join, waiting on both branch tips.
