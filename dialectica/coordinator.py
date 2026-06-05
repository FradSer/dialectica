"""Tree-of-Thoughts search engine.

The Coordinator owns the search *control flow* (build root -> expand frontier ->
score -> select -> synthesize) but delegates every decision to injected,
swappable components: a ``Generator``, an ``Evaluator``, a ``Selector`` and a
``Synthesizer``. Swap any of them to retarget the engine without touching this
file — that is what makes it general-purpose rather than a single hardcoded
ToT+GAN pipeline.
"""

import logging
from datetime import datetime
from typing import Any

from .models import ThoughtData, score_of
from .protocols import Evaluator, Generator, Selector, Synthesizer
from .validation import validate_thought_node

logger = logging.getLogger(__name__)


class Coordinator:
    """Runs a beam-style tree search using pluggable stage components.

    Phases:
    1. Initialize - create the root, expand it into strategies, score them.
    2. Explore    - iteratively select the frontier, expand, score, re-select.
    3. Synthesize - combine the evaluated thoughts into a final answer.
    """

    def __init__(
        self,
        problem: str,
        generator: Generator,
        evaluator: Evaluator,
        selector: Selector,
        synthesizer: Synthesizer,
        max_depth: int = 4,
        score_threshold: float = 7.0,
    ):
        self.problem = problem
        self.generator = generator
        self.evaluator = evaluator
        self.selector = selector
        self.synthesizer = synthesizer
        self.max_depth = max_depth
        self.score_threshold = score_threshold

        # State
        self.thought_tree: dict[str, ThoughtData] = {}
        self.active_beam: list[str] = []

        logger.info(f"Coordinator initialized for problem: {problem[:50]}...")

    async def run(self) -> dict[str, Any]:
        """Execute the full search and return the answer plus tree and stats."""
        start_time = datetime.now()

        logger.info("Phase 1: Initializing thought tree")
        await self._initialize()

        logger.info("Phase 2: Exploring with beam search")
        await self._explore()

        logger.info("Phase 3: Synthesizing final answer")
        final_answer = await self.synthesizer.synthesize(
            self.problem, list(self.thought_tree.values())
        )

        duration = (datetime.now() - start_time).total_seconds()
        return {
            "final_answer": final_answer,
            "thought_tree": {k: v.model_dump() for k, v in self.thought_tree.items()},
            "best_path": self._get_best_path(),
            "stats": {
                "total_thoughts": len(self.thought_tree),
                "max_depth_reached": max(t.depth for t in self.thought_tree.values()),
                "duration_seconds": duration,
            },
        }

    async def _initialize(self):
        """Phase 1: create the root, expand into strategies, score each."""
        root = self._add_node("root", parent_id=None, content=self.problem, depth=0, status="active")

        logger.info("Generating initial strategies")
        strategies = await self.generator.expand(root, self.problem)

        strategy_ids = []
        for i, strategy in enumerate(strategies):
            node = self._add_node(f"root_s{i}", parent_id="root", content=strategy, depth=1)
            if node is not None:
                strategy_ids.append(node.thoughtId)

        # Score strategies before beam selection so the beam reflects merit,
        # not generation order. The beam is the strategies clearing the bar.
        self.active_beam = []
        for sid in strategy_ids:
            score = await self._evaluate_node(self.thought_tree[sid], self.problem)
            if score >= self.score_threshold:
                self.active_beam.append(sid)

        # Don't stall the whole run if nothing cleared the bar: seed exploration
        # with the best strategies the selector would keep.
        if not self.active_beam and strategy_ids:
            kept = self.selector.select([self.thought_tree[sid] for sid in strategy_ids])
            self.active_beam = [n.thoughtId for n in kept]
            logger.info("No strategy passed threshold; seeding beam with top %d", len(self.active_beam))

        logger.info(
            "Scored %d strategies; %d entered the beam", len(strategy_ids), len(self.active_beam)
        )

    async def _explore(self):
        """Phase 2: beam search — select, expand, score, repeat."""
        iteration = 0
        while self.active_beam and iteration < self.max_depth:
            iteration += 1
            logger.info(f"Explore iteration {iteration}, beam size: {len(self.active_beam)}")

            frontier = self.selector.select([self.thought_tree[nid] for nid in self.active_beam])

            new_beam: list[str] = []
            for parent in frontier:
                if parent.depth >= self.max_depth:
                    continue

                children = await self.generator.expand(parent, self.problem)
                for i, content in enumerate(children):
                    child = self._add_node(
                        f"{parent.thoughtId}_c{i}",
                        parent_id=parent.thoughtId,
                        content=content,
                        depth=parent.depth + 1,
                    )
                    if child is None:
                        continue
                    score = await self._evaluate_node(child, parent.thought)
                    if score >= self.score_threshold:
                        new_beam.append(child.thoughtId)

            self.active_beam = new_beam
            logger.info(f"Iteration {iteration} complete, new beam size: {len(self.active_beam)}")

            if not self.active_beam:
                logger.info("No candidates meet threshold, stopping exploration")
                break

    async def _evaluate_node(self, node: ThoughtData, parent_thought: str) -> float:
        """Score ``node`` via the evaluator, persisting the refined thought.

        The evaluator scores the *refined* thought, so the node's text is
        updated to that refined version — otherwise synthesis would run on the
        original wording while reporting the improved score.
        """
        result = await self.evaluator.evaluate(
            thought_content=node.thought,
            context={
                "problem": self.problem,
                "parent_thought": parent_thought,
                "depth": node.depth,
            },
        )
        node.thought = result.refined_thought or node.thought
        node.evaluationScore = result.score
        node.status = "evaluated"
        node.adversarialRounds = result.adversarial_rounds
        node.refinementHistory = result.history
        return result.score

    def _add_node(
        self,
        node_id: str,
        parent_id: str | None,
        content: str,
        depth: int,
        status: str = "generated",
    ) -> ThoughtData | None:
        """Validate and insert a node; return it, or None if validation fails."""
        node = validate_thought_node(
            thought_id=node_id,
            parent_id=parent_id,
            content=content,
            depth=depth,
            status=status,
        )
        if node is None:
            if node_id == "root":
                raise ValueError(f"Root node validation failed for content: {content!r}")
            logger.warning("Skipping invalid node %s", node_id)
            return None
        self.thought_tree[node_id] = node
        return node

    def _get_best_path(self) -> list[str]:
        """Get the path from root to the highest-scoring evaluated node."""
        if not self.thought_tree:
            return []

        scored = [t for t in self.thought_tree.values() if t.evaluationScore is not None]
        if not scored:
            return ["root"] if "root" in self.thought_tree else []

        best = max(scored, key=score_of)
        path = []
        current_id: str | None = best.thoughtId
        while current_id:
            path.append(current_id)
            current = self.thought_tree.get(current_id)
            current_id = current.parentId if current else None

        return list(reversed(path))
