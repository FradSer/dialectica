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
from .gan_evaluator import DEFAULT_EVALUATION_CRITERIA, AdversarialEvaluator
from .generation import LlmGenerator
from .llm_config import get_model_config
from .models import DiscriminatorVerdict
from .protocols import Evaluator, Generator, Selector, Synthesizer
from .selection import BeamSearch
from .synthesis import LlmSynthesizer

# As a library, Dialectica does not configure global logging — the consuming
# application owns that (just as it owns env setup).
logger = logging.getLogger(__name__)


def build_default_components(
    beam_width: int = 2,
    max_gan_rounds: int = 2,
    score_threshold: float = 7.0,
    synthesizer_model: Optional[str] = None,
    gan_score_threshold: Optional[float] = None,
    criteria: Optional[str] = None,
    structured_output: bool = True,
) -> tuple[Generator, Evaluator, Selector, Synthesizer]:
    """Build the default (generator, evaluator, selector, synthesizer).

    The generator agent is shared with the evaluator so it is created once and
    reused for both generation and GAN refinement.

    ``score_threshold`` gates beam admission; ``gan_score_threshold`` (default:
    same value) is the separate "good enough, stop refining" bar for the GAN
    loop — raise it to keep refining thoughts that would already enter the
    beam. ``criteria`` is the discriminator's evaluation rubric; it steers
    answer content, not just selection.
    """
    generator_agent = create_agent(
        role="Generator",
        role_name="Generator",
        model_config=get_model_config("GENERATOR"),
    )
    # Some backends (e.g. gemma API variants) break on enforced JSON mode;
    # without a schema the discriminator prompt still demands JSON and the
    # parser handles fences/escapes.
    discriminator_agent = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        model_config=get_model_config("DISCRIMINATOR"),
        output_schema=DiscriminatorVerdict if structured_output else None,
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
        score_threshold=(
            gan_score_threshold if gan_score_threshold is not None else score_threshold
        ),
        criteria=criteria if criteria is not None else DEFAULT_EVALUATION_CRITERIA,
    )
    selector = BeamSearch(width=beam_width)
    synthesizer = LlmSynthesizer(synthesizer_agent)
    return generator, evaluator, selector, synthesizer


def create_coordinator(
    problem: str,
    max_depth: int = 2,
    beam_width: int = 2,
    max_gan_rounds: int = 2,
    score_threshold: float = 7.0,
    synthesizer_model: Optional[str] = None,
    gan_score_threshold: Optional[float] = None,
    criteria: Optional[str] = None,
    structured_output: bool = True,
) -> Coordinator:
    """Create a Coordinator wired with the default ToT + GAN components.

    Args:
        problem: The problem statement to solve
        max_depth: Maximum depth of the thought tree (default: 4)
        beam_width: Number of top candidates the beam keeps (default: 3)
        max_gan_rounds: Maximum adversarial refinement rounds (default: 3)
        score_threshold: Minimum score for a thought to enter the beam (default: 7.0)
        synthesizer_model: Optional specific model for synthesis
        gan_score_threshold: "Good enough, stop refining" bar for the GAN loop
            (default: same as score_threshold)
        criteria: Discriminator evaluation rubric — steers answer content
            (default: DEFAULT_EVALUATION_CRITERIA, feasibility-anchored)

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
        gan_score_threshold=gan_score_threshold,
        criteria=criteria,
        structured_output=structured_output,
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
