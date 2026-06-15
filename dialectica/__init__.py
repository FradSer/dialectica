"""
Dialectica — a dialectical reasoning engine.

The soul is the dialectic its name promises: **thesis → antithesis →
synthesis**, run intelligently (name the problem's core tension, oppose it
with a complete rival rather than a critique, synthesize beyond both, spiral
until convergence). ``create_dialectic_engine`` is the recommended entry point.

A legacy Tree-of-Thoughts + GAN beam-search pipeline is also shipped
(``create_engine`` / ``create_coordinator``) as the prior-generation kernel and
the baseline the dialectic is measured against; every stage is a swappable
``Protocol`` (Generator / Evaluator / Selector / Synthesizer).

Example:
    from dialectica import create_dialectic_engine

    engine = create_dialectic_engine("Your problem here")
    result = await engine.run()


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
from .coordinator import Coordinator
from .dialectic import DialecticEngine, create_dialectic_engine
from .repair import IterativeRepairEngine, create_repair_engine
from .gan_evaluator import (
    DEFAULT_EVALUATION_CRITERIA,
    AdversarialEvaluator,
    SinglePassEvaluator,
)
from .generation import LlmGenerator
from .models import DiscriminatorVerdict, EvaluationResult, ThoughtData
from .protocols import Evaluator, Generator, Selector, Synthesizer
from .selection import BeamSearch, GreedySearch
from .synthesis import LlmSynthesizer

__all__ = [
    # The dialectic kernel — the recommended entry point
    "create_dialectic_engine",
    "DialecticEngine",
    # Execution-guided repair — verifier-in-the-loop engine for verifiable tasks
    "create_repair_engine",
    "IterativeRepairEngine",
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

__version__ = "0.4.0"
