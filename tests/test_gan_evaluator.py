"""Tests for the GAN adversarial evaluation loop — mocked LLM, no network."""

from unittest.mock import patch

import pytest

from dialectica.agent_factory import create_agent
from dialectica.gan_evaluator import AdversarialEvaluator, SinglePassEvaluator, parse_verdict
from dialectica.models import DiscriminatorVerdict

from helpers import make_call_agent, verdict_json


@pytest.fixture
def evaluator():
    generator = create_agent(role="Generator", role_name="Generator")
    discriminator = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        output_schema=DiscriminatorVerdict,
    )
    return AdversarialEvaluator(
        generator=generator,
        discriminator=discriminator,
        max_rounds=3,
        score_threshold=7.0,
    )


def test_parse_valid_structured_verdict():
    result = parse_verdict(verdict_json(8.0, flaws=["f"]))
    assert result.score == 8.0
    assert result.flaws == ["f"]


def test_parse_malformed_verdict_scores_zero():
    result = parse_verdict("this is not json")
    assert result.score == 0.0
    assert "Unparseable" in result.reasoning


async def test_threshold_reached_first_round_skips_refinement(evaluator):
    fake = make_call_agent([{"score": 8.0}])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("a thought", {"problem": "p"})
    assert result.score == 8.0
    assert result.adversarial_rounds == 1
    assert len(result.history) == 1


async def test_low_score_triggers_refinement_then_passes(evaluator):
    fake = make_call_agent([{"score": 5.0}, {"score": 9.0}], refined="REFINED")
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("a thought", {"problem": "p"})
    assert result.score == 9.0
    assert result.adversarial_rounds == 2
    # second round must have evaluated the refined thought
    assert result.history[1]["thought"] == "REFINED"


async def test_should_terminate_exits_early(evaluator):
    fake = make_call_agent([{"score": 2.0, "should_terminate": True}])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("a thought", {"problem": "p"})
    assert result.should_terminate is True
    assert result.adversarial_rounds == 1


async def test_refined_thought_is_returned(evaluator):
    fake = make_call_agent([{"score": 5.0}, {"score": 9.0}], refined="REFINED V2")
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("original", {"problem": "p"})
    # score belongs to the refined thought, so that text must come back
    assert result.refined_thought == "REFINED V2"


async def test_refined_thought_is_original_when_passing_first_round(evaluator):
    fake = make_call_agent([{"score": 9.0}])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("original thought", {"problem": "p"})
    assert result.refined_thought == "original thought"


async def test_keeps_best_round_when_refinement_degrades():
    # Regression: refinement can make a thought worse; the loop must keep the
    # best-scoring round, not the last one.
    generator = create_agent(role="Generator", role_name="Generator")
    discriminator = create_agent(
        role="Discriminator", role_name="Discriminator", output_schema=DiscriminatorVerdict
    )
    evaluator = AdversarialEvaluator(
        generator=generator, discriminator=discriminator, max_rounds=2, score_threshold=9.0
    )
    fake = make_call_agent([{"score": 7.5}, {"score": 3.0}], refined="WORSE VERSION")
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("original thought", {"problem": "p"})
    assert result.score == 7.5
    assert result.refined_thought == "original thought"
    assert result.adversarial_rounds == 2
    assert len(result.history) == 2


async def test_single_pass_evaluator_scores_once_no_refinement():
    discriminator = create_agent(
        role="Discriminator", role_name="Discriminator", output_schema=DiscriminatorVerdict
    )
    evaluator = SinglePassEvaluator(discriminator)
    fake = make_call_agent([{"score": 6.0}])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("a thought", {"problem": "p"})
    assert result.score == 6.0
    assert result.adversarial_rounds == 1
    assert result.refined_thought == "a thought"
    assert len(result.history) == 1


async def test_max_rounds_reached_returns_last_eval():
    generator = create_agent(role="Generator", role_name="Generator")
    discriminator = create_agent(
        role="Discriminator", role_name="Discriminator", output_schema=DiscriminatorVerdict
    )
    evaluator = AdversarialEvaluator(
        generator=generator, discriminator=discriminator, max_rounds=2, score_threshold=7.0
    )
    fake = make_call_agent([{"score": 4.0}, {"score": 5.0}])
    with patch("dialectica.agent_runtime.run_agent", fake):
        result = await evaluator.evaluate("a thought", {"problem": "p"})
    assert result.score == 5.0
    assert result.adversarial_rounds == 2
    assert len(result.history) == 2
