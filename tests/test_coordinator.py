"""Engine control-flow tests for the Coordinator.

These inject fake stage components directly (no LLM, no patching) to exercise
the real search logic: strategy scoring, beam selection, pruning, refined-thought
persistence, and synthesis hand-off. This is the payoff of the pluggable design.
"""

from dialectica.coordinator import Coordinator
from dialectica.models import EvaluationResult, ThoughtData
from dialectica.selection import BeamSearch, GreedySearch


class FakeGenerator:
    """Returns fixed strategy/child lists depending on node depth."""

    def __init__(self, strategies, children):
        self.strategies = list(strategies)
        self.children = list(children)

    async def expand(self, parent: ThoughtData, problem: str) -> list[str]:
        return self.strategies if parent.depth == 0 else self.children


class ConstantEvaluator:
    """Scores every thought the same; optionally rewrites it to ``refined``."""

    def __init__(self, score: float, refined: str | None = None):
        self.score = score
        self.refined = refined

    async def evaluate(self, thought_content: str, context: dict) -> EvaluationResult:
        refined = self.refined if self.refined is not None else thought_content
        return EvaluationResult(
            score=self.score,
            refined_thought=refined,
            adversarial_rounds=1,
            history=[{"round": 1, "thought": refined, "score": self.score}],
        )


class FakeSynthesizer:
    def __init__(self, answer: str = "FINAL"):
        self.answer = answer
        self.seen: list[ThoughtData] | None = None

    async def synthesize(self, problem: str, thoughts: list[ThoughtData]) -> str:
        self.seen = list(thoughts)
        return self.answer


def make_coordinator(
    *,
    score=8.0,
    refined=None,
    strategies=("S1", "S2", "S3"),
    children=("C1", "C2", "C3"),
    selector=None,
    synthesizer=None,
    max_depth=2,
    threshold=7.0,
):
    return Coordinator(
        problem="p",
        generator=FakeGenerator(strategies, children),
        evaluator=ConstantEvaluator(score, refined),
        selector=selector or BeamSearch(width=2),
        synthesizer=synthesizer or FakeSynthesizer(),
        max_depth=max_depth,
        score_threshold=threshold,
    )


async def test_happy_path_builds_tree_and_synthesizes():
    coordinator = make_coordinator(score=8.0)
    result = await coordinator.run()

    assert result["final_answer"] == "FINAL"
    # root + 3 strategies + (2 expanded parents * 3 children) = 10
    assert result["stats"]["total_thoughts"] == 10
    assert result["stats"]["max_depth_reached"] == 2
    evaluated = [t for t in coordinator.thought_tree.values() if t.status == "evaluated"]
    assert evaluated and all(t.evaluationScore == 8.0 for t in evaluated)


async def test_initial_strategies_are_scored():
    # Regression: strategies used to enter the beam by generation order, unscored.
    coordinator = make_coordinator(score=8.0)
    await coordinator.run()
    strategies = [t for t in coordinator.thought_tree.values() if t.depth == 1]
    assert strategies
    assert all(t.evaluationScore == 8.0 and t.status == "evaluated" for t in strategies)


async def test_best_path_starts_at_root():
    coordinator = make_coordinator(score=8.0)
    result = await coordinator.run()
    assert result["best_path"][0] == "root"
    assert len(result["best_path"]) >= 2


async def test_low_scores_prune_the_beam():
    coordinator = make_coordinator(score=3.0)
    result = await coordinator.run()
    assert coordinator.active_beam == []
    evaluated = [t for t in coordinator.thought_tree.values() if t.status == "evaluated"]
    assert evaluated and all(t.evaluationScore == 3.0 for t in evaluated)
    assert result["final_answer"] == "FINAL"


async def test_refined_thought_persisted_on_nodes():
    # Regression: the refined (scored) thought must replace the original wording.
    coordinator = make_coordinator(score=8.0, refined="REFINED")
    await coordinator.run()
    evaluated = [t for t in coordinator.thought_tree.values() if t.status == "evaluated"]
    assert evaluated and all(t.thought == "REFINED" for t in evaluated)


async def test_selector_is_pluggable():
    # Greedy (width 1) expands a single strategy -> fewer children than beam width 2.
    greedy = make_coordinator(score=8.0, selector=GreedySearch())
    beam = make_coordinator(score=8.0, selector=BeamSearch(width=2))
    greedy_result = await greedy.run()
    beam_result = await beam.run()
    assert greedy_result["stats"]["total_thoughts"] < beam_result["stats"]["total_thoughts"]


async def test_synthesizer_receives_evaluated_thoughts():
    synth = FakeSynthesizer(answer="DONE")
    coordinator = make_coordinator(score=8.0, synthesizer=synth)
    result = await coordinator.run()
    assert result["final_answer"] == "DONE"
    assert synth.seen and any(t.status == "evaluated" for t in synth.seen)
