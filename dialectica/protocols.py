"""Pluggable component interfaces for the Tree-of-Thoughts engine.

The Coordinator orchestrates purely against these protocols, so each stage can
be swapped independently: a different generation strategy, a cheaper or
stronger evaluator, a different search/selection policy, or a custom
synthesizer — without touching the engine. This is what makes the engine
general-purpose (the `/workflows`-style goal) rather than a single hardcoded
ToT+GAN pipeline.

These are ``typing.Protocol`` (structural) types: any object with matching
methods satisfies them; implementations need not subclass anything.
"""

from typing import Protocol, runtime_checkable

from .models import EvaluationResult, ThoughtData


@runtime_checkable
class Generator(Protocol):
    """Expands a node into candidate child thought texts."""

    async def expand(self, parent: ThoughtData, problem: str) -> list[str]:
        """Return new candidate thoughts branching from ``parent``.

        For the root node (``parent.depth == 0``) these are top-level
        strategies; for deeper nodes they are concrete next steps.
        """
        ...


@runtime_checkable
class Evaluator(Protocol):
    """Scores a thought, optionally refining it."""

    async def evaluate(self, thought_content: str, context: dict) -> EvaluationResult:
        """Score ``thought_content`` and return a structured result.

        ``EvaluationResult.refined_thought`` carries the text the score applies
        to (an evaluator may improve the thought before scoring it).
        """
        ...


@runtime_checkable
class Selector(Protocol):
    """Chooses which scored nodes advance to the next search frontier."""

    def select(self, nodes: list[ThoughtData]) -> list[ThoughtData]:
        """Return the subset of ``nodes`` to keep exploring."""
        ...


@runtime_checkable
class Synthesizer(Protocol):
    """Combines explored thoughts into a final answer."""

    async def synthesize(self, problem: str, thoughts: list[ThoughtData]) -> str:
        """Produce the final answer from the evaluated ``thoughts``."""
        ...
