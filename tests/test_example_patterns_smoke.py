"""Smoke tests for examples/patterns/ — a regression net, not a spec.

Each demoted engine got full BDD coverage while it was shipped API; now that
it's reference-only code, one mocked end-to-end run per pattern is enough to
catch "the example no longer imports/executes" without re-litigating every
roster-rotation/circuit-breaker/early-exit edge case the original suites
already exercised (and which the honesty-gate evals continue to measure
against a live model).
"""

import asyncio
import json
from unittest.mock import patch

from tests.helpers import make_ensemble_fake


def test_agentic_pattern_runs_a_tool_using_stage():
    from examples.patterns.agentic_pattern import create_agentic_engine

    async def fake(agent, instruction: str) -> str:
        return "task complete"

    def probe(x: int) -> int:
        return x + 1

    engine = create_agentic_engine("do the task", tools=[probe])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = asyncio.run(engine.run())

    assert result["final_answer"] == "task complete"


def test_dialectic_pattern_runs_the_norational_tension_shortcircuit():
    from examples.patterns.dialectic_pattern import create_dialectic_engine

    responses = iter(["NONE", "the direct answer"])

    async def fake(agent, instruction: str) -> str:
        return next(responses)

    engine = create_dialectic_engine("what is 2 + 2?")
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = asyncio.run(engine.run())

    assert result["dialecticized"] is False
    assert result["final_answer"] == "the direct answer"


def test_ensemble_pattern_runs_a_solved_roster_call():
    from examples.patterns.ensemble_pattern import create_ensemble_engine

    fake, counter = make_ensemble_fake({"A": ["good answer"]})

    def scorer(answer: str) -> float:
        return 1.0 if answer == "good answer" else 0.0

    engine = create_ensemble_engine("solve it", scorer=scorer, models=["A"])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = asyncio.run(engine.run())

    assert result["passed"] is True
    assert result["final_answer"] == "good answer"
    assert counter["A"] == 1


def test_verdict_coerces_objectshaped_flaws_and_suggestions():
    """Regression guard: some backends return flaws/suggestions as objects
    (e.g. {"category": ..., "text": ...}) instead of plain strings. Losing the
    coercion silently degrades every such verdict to clamp_score(None) == 0.0.
    """
    from examples.patterns._scoring import Verdict

    verdict = Verdict.model_validate(
        {
            "score": 6.0,
            "flaws": [{"category": "Feasibility", "text": "too vague"}],
            "suggestions": [{"suggestion": "add numbers"}, "plain string ok"],
            "should_terminate": False,
            "reasoning": "ok",
        }
    )
    assert verdict.flaws == ["too vague"]
    assert verdict.suggestions == ["add numbers", "plain string ok"]


def test_tot_gan_pattern_runs_a_singledepth_beam():
    from examples.patterns.tot_gan_pattern import create_engine

    verdict = json.dumps(
        {
            "score": 8.0,
            "flaws": [],
            "suggestions": [],
            "should_terminate": False,
            "reasoning": "ok",
        }
    )

    async def fake(agent, instruction: str) -> str:
        if agent.name == "generator":
            return "1. Strategy one\n2. Strategy two"
        if agent.name == "discriminator":
            return verdict
        if agent.name == "synthesizer":
            return "final synthesized answer"
        return "ok"

    engine = create_engine("solve it", max_depth=1, beam_width=1, max_gan_rounds=1)
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = asyncio.run(engine.run())

    assert result["final_answer"] == "final synthesized answer"
    assert result["stats"]["total_thoughts"] >= 1
