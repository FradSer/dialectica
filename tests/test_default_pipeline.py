"""Integration test: the default composition wired by create_coordinator.

Exercises LlmGenerator + AdversarialEvaluator + BeamSearch + LlmSynthesizer
together, with the single LLM seam (agent_runtime.run_agent) mocked.
"""

from contextlib import contextmanager
from unittest.mock import patch

from dialectica.agent import create_coordinator

from helpers import make_constant_call_agent


@contextmanager
def patched_llm(fake):
    with patch("dialectica.agent_runtime.run_agent", fake):
        yield


async def test_default_pipeline_runs_end_to_end():
    coordinator = create_coordinator(
        problem="How do we test the default composition?",
        max_depth=2,
        beam_width=2,
        max_gan_rounds=1,
        score_threshold=7.0,
    )
    with patched_llm(make_constant_call_agent(8.0)):
        result = await coordinator.run()

    assert result["final_answer"] == "FINAL SYNTHESIZED ANSWER"
    assert result["stats"]["total_thoughts"] == 10
    assert result["best_path"][0] == "root"
    evaluated = [t for t in coordinator.thought_tree.values() if t.status == "evaluated"]
    assert evaluated and all(t.evaluationScore == 8.0 for t in evaluated)


async def test_default_pipeline_prunes_low_scores():
    coordinator = create_coordinator(
        problem="p", max_depth=2, beam_width=2, max_gan_rounds=1, score_threshold=7.0
    )
    with patched_llm(make_constant_call_agent(3.0)):
        result = await coordinator.run()
    assert coordinator.active_beam == []
    assert result["final_answer"] == "FINAL SYNTHESIZED ANSWER"
