"""Claim selection is bounded, independent of full traces, and never invents an answer."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from dialectica import BudgetExhausted, Workflow
from dialectica.agent_runtime import AgentResponse, TokenUsage
from examples.patterns.claim_falsification_pattern import (
    ClaimCandidate,
    ClaimVerdicts,
    create_claim_falsification_engine,
    select_candidate,
)


def candidate(answer):
    return ClaimCandidate(answer=answer, claims=[f"claim {i}" for i in range(5)])


def test_reliability_can_overturn_consensus_but_never_candidate_coverage():
    candidates = [candidate("wrong"), candidate("wrong"), candidate("right")]
    verdicts = [
        ClaimVerdicts(survived=[True, True, False, False, False]),
        ClaimVerdicts(survived=[True, True, False, False, False]),
        ClaimVerdicts(survived=[True] * 5),
    ]
    assert select_candidate(candidates, verdicts) == "right"
    assert select_candidate(candidates[:2], verdicts[:2]) == "wrong"
    zeros = [ClaimVerdicts(survived=[False] * 5)] * 3
    assert select_candidate(candidates, zeros) == "wrong"


def test_equivalent_answers_combine_support():
    candidates = [candidate("[1,2]"), candidate("[2,1]"), candidate("[3]")]
    verdicts = [ClaimVerdicts(survived=[True] * 5)] * 3
    assert (
        select_candidate(
            candidates, verdicts, lambda text: tuple(sorted(json.loads(text)))
        )
        == "[1,2]"
    )
    with pytest.raises(ValueError):
        select_candidate(candidates, verdicts[:1])


def test_unparseable_predictions_are_omitted_before_weighted_selection():
    candidates = [candidate("invalid"), candidate("[1]")]
    verdicts = [ClaimVerdicts(survived=[True] * 5)] * 2

    def parse(answer):
        return tuple(json.loads(answer))

    assert select_candidate(candidates, verdicts, parse) == "[1]"
    with pytest.raises(ValueError, match="parsed"):
        select_candidate(candidates[:1], verdicts[:1], parse)


async def test_assessment_sees_only_problem_and_claims_and_joins_outer_budget():
    first = candidate("PRIVATE ANSWER A")
    second = candidate("PRIVATE ANSWER B")
    mocked = AsyncMock(
        side_effect=[
            first,
            second,
            ClaimVerdicts(survived=[False] * 5),
            ClaimVerdicts(survived=[True] * 5),
        ]
    )
    with patch("examples.patterns.claim_falsification_pattern.wf.agent", mocked):
        result = await create_claim_falsification_engine(
            "problem facts", samples=2
        ).run()
    assert result["final_answer"] == second.answer
    assert result["candidates"] == [first.model_dump(), second.model_dump()]
    assert mocked.await_count == 4
    for call in mocked.await_args_list[2:]:
        prompt = call.args[0]
        assert "problem facts" in prompt
        assert "claim 0" in prompt
        assert "PRIVATE ANSWER" not in prompt
        assert call.kwargs["sees"] == []


async def test_malformed_measurement_is_explicit_failure():
    with (
        patch(
            "examples.patterns.claim_falsification_pattern.wf.agent",
            AsyncMock(return_value=None),
        ),
        pytest.raises(TypeError, match="candidate"),
    ):
        await create_claim_falsification_engine("problem", samples=1).run()


async def test_all_generation_and_assessment_calls_charge_outer_budget():
    first = candidate("answer").model_dump_json()
    verdict = ClaimVerdicts(survived=[True] * 5).model_dump_json()
    transport = AsyncMock(
        side_effect=[
            AgentResponse(text, TokenUsage(total_tokens=10))
            for text in [first, first, verdict, verdict]
        ]
    )

    async def script():
        return await create_claim_falsification_engine("problem", samples=2).run()

    with (
        patch("dialectica.agent_runtime.run_agent", transport),
        pytest.raises(BudgetExhausted),
    ):
        await Workflow(script, budget_total=3).run()
    assert transport.await_count == 3
