"""Judge disagreement and malformed measurements are not quality ties."""

from unittest.mock import AsyncMock, patch

import pytest

from evals.evidence_eval import EvidenceVerdict, compare_answers


async def test_position_disagreement_is_explicitly_inconclusive():
    verdicts = AsyncMock(
        side_effect=[
            EvidenceVerdict(winner="A", reasoning="first"),
            EvidenceVerdict(winner="A", reasoning="position bias"),
        ]
    )
    with patch("evals.evidence_eval.wf.agent", verdicts):
        result = await compare_answers(
            "problem", "candidate", "baseline", "google:test"
        )
    assert result["status"] == "position_disagreement"
    assert result["winner"] is None


async def test_consistent_swapped_verdict_identifies_the_same_answer():
    verdicts = AsyncMock(
        side_effect=[
            EvidenceVerdict(winner="A", reasoning="better"),
            EvidenceVerdict(winner="B", reasoning="better"),
        ]
    )
    with patch("evals.evidence_eval.wf.agent", verdicts):
        result = await compare_answers(
            "problem", "candidate", "baseline", "google:test"
        )
    assert result["winner"] == "candidate"
    assert result["status"] == "valid"


async def test_malformed_or_abstaining_judge_cannot_manufacture_tie():
    with (
        patch("evals.evidence_eval.wf.agent", AsyncMock(return_value=None)),
        pytest.raises(TypeError),
    ):
        await compare_answers("problem", "candidate", "baseline", "google:test")
    with patch(
        "evals.evidence_eval.wf.agent",
        AsyncMock(
            return_value=EvidenceVerdict(winner="abstain", reasoning="cannot judge")
        ),
    ):
        result = await compare_answers(
            "problem", "candidate", "baseline", "google:test"
        )
    assert result["winner"] is None
    assert result["status"] == "abstained"
