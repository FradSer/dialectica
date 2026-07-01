"""
Dialectica — reasoning engines, kept honest by controlled evals (see README).

The hierarchy the data justifies:

- ``create_agentic_engine`` — THE GENUINE WIN. A tool-using loop (act -> observe
  -> iterate): inject tools and the agent works until the task is objectively
  done. The one engine that lets a model do what a single forward pass CANNOT —
  it adds capability, not quality (measured 8/8 vs a single call's 0/8 for a
  small model on tasks requiring interaction).
- ``create_ensemble_engine`` — AB-MCTS-lite adaptive search over a heterogeneous
  roster ranked by an injected scorer. ON PROBATION: the honesty gate (README
  Evaluation finding #5) showed the ensemble *does* improve answer robustness on
  open-ended tasks (3-1-2 vs a prompt-matched single call under a blind judge),
  but the gain is attributable to **roster heterogeneity, not the scorer's
  signal** — a blind-pick arm tied it. The float scorer adds no measurable lift
  over no-scorer multi-model best-of-N. Verdict: CUT per H1's signal-attribution
  clause; kept for study.
- ``create_repair_engine`` — verifier-in-the-loop for verifiable tasks. Ties
  matched-cost best-of-K on pass-rate but reaches it far cheaper (short-circuits
  on success). Verifier is an injected ``Callable[[answer], (passed, feedback)]``.
- ``create_dialectic_engine`` — thesis -> antithesis -> synthesis. A pure-LLM
  scaffold; it does NOT beat a prompt-matched single call on result quality
  (adds no information). Its value is content-steering via criteria + an
  auditable trade-off trace.
- ``create_engine`` / ``create_coordinator`` — legacy Tree-of-Thoughts + GAN
  beam search, kept as a baseline; every stage is a swappable ``Protocol``.

Example:
    from dialectica import create_agentic_engine

    engine = create_agentic_engine("Your task", tools=[read_file, run_tests])
    result = await engine.run()  # {"final_answer"}; tools do the acting


Configuration is read from ``os.environ`` — as a library, Dialectica does NOT
load ``.env`` itself; the consuming application owns environment setup.
"""

from .agent import (
    Engine,
    build_default_components,
    create_coordinator,
    create_engine,
    run_tot_workflow,
)
from .agent_factory import ROLE_TEMPLATES, create_agent
from .agentic import AgenticEngine, create_agentic_engine
from .coordinator import Coordinator
from .dialectic import DialecticEngine, create_dialectic_engine
from .ensemble import EnsembleSearchEngine, create_ensemble_engine
from .gan_evaluator import (
    DEFAULT_EVALUATION_CRITERIA,
    AdversarialEvaluator,
    SinglePassEvaluator,
)
from .generation import LlmGenerator
from .models import DiscriminatorVerdict, EvaluationResult, ThoughtData
from .protocols import Evaluator, Generator, Selector, Synthesizer
from .repair import IterativeRepairEngine, create_repair_engine
from .selection import BeamSearch, GreedySearch
from .synthesis import LlmSynthesizer
from .workflow import (
    Budget,
    BudgetExhausted,
    Workflow,
    agent,
    args,
    budget,
    log,
    parallel,
    phase,
    pipeline,
)

__all__ = [
    # Agentic engine — tool-using loop; adds capability (act/observe/iterate)
    # a single forward pass structurally lacks
    "create_agentic_engine",
    "AgenticEngine",
    # Ensemble search — AB-MCTS-lite over a heterogeneous roster; scorer-in-the-
    # loop (float rank = ground truth a single pass lacks)
    "create_ensemble_engine",
    "EnsembleSearchEngine",
    # Execution-guided repair — verifier-in-the-loop; cost-efficient reliability
    "create_repair_engine",
    "IterativeRepairEngine",
    # Dialectic — open-ended steering + auditable trade-off trace (not a
    # single-call quality booster)
    "create_dialectic_engine",
    "DialecticEngine",
    # Legacy ToT + GAN engine (prior generation / baseline)
    "create_engine",
    "Engine",
    "build_default_components",
    "run_tot_workflow",
    # Backward-compatible aliases
    "create_coordinator",
    "Coordinator",
    # Workflow primitives — a composable multi-agent runtime for meta-tasks
    # (research/review/planning/design). Orchestration layer, NOT a
    # self-contained-quality engine (see README Evaluation).
    "Workflow",
    "Budget",
    "BudgetExhausted",
    "agent",
    "parallel",
    "pipeline",
    "phase",
    "log",
    "budget",
    "args",
    # Stage protocols (the pluggable interfaces)
    "Generator",
    "Evaluator",
    "Selector",
    "Synthesizer",
    # Default stage implementations
    "LlmGenerator",
    "AdversarialEvaluator",
    "SinglePassEvaluator",
    "DEFAULT_EVALUATION_CRITERIA",
    "BeamSearch",
    "GreedySearch",
    "LlmSynthesizer",
    # Data models
    "ThoughtData",
    "EvaluationResult",
    "DiscriminatorVerdict",
    # Agent creation
    "create_agent",
    "ROLE_TEMPLATES",
]

__version__ = "0.6.0"
