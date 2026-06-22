"""Unit tests for the data models — pure, no LLM calls."""

import pytest
from pydantic import ValidationError

from dialectica.models import (
    DiscriminatorVerdict,
    EvaluationResult,
    ThoughtData,
)


def test_discriminator_verdict_parses_from_json():
    verdict = DiscriminatorVerdict.model_validate_json(
        '{"score": 7.5, "flaws": ["a"], "suggestions": ["b"], '
        '"should_terminate": false, "reasoning": "fine"}'
    )
    assert verdict.score == 7.5
    assert verdict.flaws == ["a"]
    assert verdict.suggestions == ["b"]
    assert verdict.should_terminate is False
    assert verdict.reasoning == "fine"


def test_discriminator_verdict_fills_defaults_for_missing_fields():
    verdict = DiscriminatorVerdict.model_validate_json('{"score": 4}')
    assert verdict.score == 4
    assert verdict.flaws == []
    assert verdict.suggestions == []
    assert verdict.should_terminate is False


def test_discriminator_verdict_coerces_object_valued_flaws():
    # Models often return flaws/suggestions as objects, not strings. Left
    # uncoerced this fails list[str] validation and (3x in a row) aborts the
    # run; the verdict must pull out the text instead of crashing.
    verdict = DiscriminatorVerdict.model_validate_json(
        '{"score": 6, '
        '"flaws": [{"category": "Feasibility", "text": "too costly"}, "plain"], '
        '"suggestions": [{"suggestion": "cut scope"}]}'
    )
    assert verdict.flaws == ["too costly", "plain"]
    assert verdict.suggestions == ["cut scope"]


def test_discriminator_verdict_schema_is_gemini_friendly():
    # extra='forbid' / numeric constraints break Gemini structured output;
    # the verdict schema must avoid both.
    schema = DiscriminatorVerdict.model_json_schema()
    score = schema["properties"]["score"]
    assert "minimum" not in score
    assert "maximum" not in score


def test_evaluation_result_from_verdict_clamps_high_score():
    verdict = DiscriminatorVerdict(score=12.0, flaws=["x"], reasoning="too high")
    result = EvaluationResult.from_verdict(verdict)
    assert result.score == 10.0
    assert result.flaws == ["x"]
    assert result.reasoning == "too high"


def test_evaluation_result_from_verdict_clamps_low_score():
    result = EvaluationResult.from_verdict(DiscriminatorVerdict(score=-3.0))
    assert result.score == 0.0


def test_evaluation_result_rejects_out_of_range_direct_construction():
    with pytest.raises(ValidationError):
        EvaluationResult(score=11.0)


def test_thought_data_round_trips():
    node = ThoughtData(thoughtId="n1", thought="hello", depth=0)
    assert node.parentId is None
    assert node.status == "active"
    assert node.to_dict()["thoughtId"] == "n1"


def test_thought_data_requires_nonempty_thought():
    with pytest.raises(ValidationError):
        ThoughtData(thoughtId="n1", thought="", depth=0)
