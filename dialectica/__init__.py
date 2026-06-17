"""
Dialectica — reasoning engines, led by execution-guided repair.

Controlled evals (see README) established the honest hierarchy:

- ``create_repair_engine`` — THE CORE. Generate -> run an objective verifier ->
  repair against the concrete failure -> retry. The only engine here that
  structurally beats a single strong-model call, because it adds what a single
  forward pass lacks: ground-truth verification. Use it for any verifiable task
  (unit tests, a schema validator, a linter, assertion-checked logic).
- ``create_dialectic_engine`` — thesis -> antithesis -> synthesis. A pure-LLM
  scaffold; it does NOT beat a prompt-matched single call on result quality (it
  rearranges the model's own thinking, adding no information). Its genuine value
  is content-steering via criteria and an auditable trade-off trace on
  open-ended sub-decisions.
- ``create_engine`` / ``create_coordinator`` — legacy Tree-of-Thoughts + GAN
  beam search, kept as a baseline; every stage is a swappable ``Protocol``.

Example:
    from dialectica import create_repair_engine

    engine = create_repair_engine("Your task", verifier=my_checker)
    result = await engine.run()  # {"final_answer", "passed", "attempts", ...}


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

__all__ = [
    # Agentic engine — tool-using loop; adds capability (act/observe/iterate)
    # a single forward pass structurally lacks
    "create_agentic_engine",
    "AgenticEngine",
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

__version__ = "0.5.0"
