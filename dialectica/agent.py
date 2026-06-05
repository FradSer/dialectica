"""
Tree of Thoughts with GAN-style Adversarial Evaluation — composition root.

``create_coordinator`` wires the default pluggable components (LLM generator,
GAN evaluator, beam-search selector, LLM synthesizer) into a ``Coordinator``.
To customize, build the components yourself and construct ``Coordinator``
directly — see ``build_default_components``.

Usage:
    from dialectica.agent import create_coordinator

    coordinator = create_coordinator("Your problem statement here")
    result = await coordinator.run()
"""

import logging
from typing import Optional

from .agent_factory import create_agent
from .coordinator import Coordinator
from .gan_evaluator import AdversarialEvaluator
from .generation import LlmGenerator
from .llm_config import get_model_config
from .models import DiscriminatorVerdict
from .protocols import Evaluator, Generator, Selector, Synthesizer
from .selection import BeamSearch
from .synthesis import LlmSynthesizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_default_components(
    beam_width: int = 3,
    max_gan_rounds: int = 3,
    score_threshold: float = 7.0,
    synthesizer_model: Optional[str] = None,
) -> tuple[Generator, Evaluator, Selector, Synthesizer]:
    """Build the default (generator, evaluator, selector, synthesizer).

    The generator agent is shared with the evaluator so it is created once and
    reused for both generation and GAN refinement.
    """
    generator_agent = create_agent(
        role="Generator",
        role_name="Generator",
        model_config=get_model_config("GENERATOR"),
    )
    discriminator_agent = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        model_config=get_model_config("DISCRIMINATOR"),
        output_schema=DiscriminatorVerdict,
    )
    synthesizer_agent = create_agent(
        role="Synthesizer",
        role_name="Synthesizer",
        model_config=synthesizer_model or get_model_config("SYNTHESIZER"),
    )

    generator = LlmGenerator(generator_agent)
    evaluator = AdversarialEvaluator(
        generator=generator_agent,
        discriminator=discriminator_agent,
        max_rounds=max_gan_rounds,
        score_threshold=score_threshold,
    )
    selector = BeamSearch(width=beam_width)
    synthesizer = LlmSynthesizer(synthesizer_agent)
    return generator, evaluator, selector, synthesizer


def create_coordinator(
    problem: str,
    max_depth: int = 4,
    beam_width: int = 3,
    max_gan_rounds: int = 3,
    score_threshold: float = 7.0,
    synthesizer_model: Optional[str] = None,
) -> Coordinator:
    """Create a Coordinator wired with the default ToT + GAN components.

    Args:
        problem: The problem statement to solve
        max_depth: Maximum depth of the thought tree (default: 4)
        beam_width: Number of top candidates the beam keeps (default: 3)
        max_gan_rounds: Maximum adversarial refinement rounds (default: 3)
        score_threshold: Minimum score for a thought to continue (default: 7.0)
        synthesizer_model: Optional specific model for synthesis

    Returns:
        Configured Coordinator instance

    Example:
        >>> coordinator = create_coordinator("Design a sustainable urban transport system")
        >>> result = await coordinator.run()
        >>> print(result["final_answer"])
    """
    logger.info(f"Creating coordinator for problem: {problem[:50]}...")

    generator, evaluator, selector, synthesizer = build_default_components(
        beam_width=beam_width,
        max_gan_rounds=max_gan_rounds,
        score_threshold=score_threshold,
        synthesizer_model=synthesizer_model,
    )
    return Coordinator(
        problem=problem,
        generator=generator,
        evaluator=evaluator,
        selector=selector,
        synthesizer=synthesizer,
        max_depth=max_depth,
        score_threshold=score_threshold,
    )


# Convenience wrapper for embedding the engine in other async code.
async def run_tot_workflow(problem: str, **kwargs):
    """Run a complete ToT workflow for a given problem.

    Convenience wrapper for frameworks that need a simple async function.

    Returns:
        Dictionary with final_answer, thought_tree, best_path, and stats
    """
    coordinator = create_coordinator(problem, **kwargs)
    return await coordinator.run()


# Canonical Dialectica names. The Coordinator/create_coordinator names are kept
# as aliases for backward compatibility.
create_engine = create_coordinator
Engine = Coordinator


__all__ = [
    "create_engine",
    "Engine",
    "build_default_components",
    "run_tot_workflow",
    # Backward-compatible aliases
    "create_coordinator",
    "Coordinator",
]
