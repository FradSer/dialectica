"""Open-ended comparisons require calibrated, independent agreeing judges."""

import json
from unittest.mock import AsyncMock, patch

from evals.evidence_ablation import aggregate_judges, generate, recorded_family, run


def test_disagreement_and_missing_calibration_are_not_ties():
    good = {"status": "valid", "winner": "candidate"}
    other = {"status": "valid", "winner": "baseline"}
    assert aggregate_judges([good, other], [True, True])["winner"] is None
    assert aggregate_judges([good, good], [True, False])["status"] == "uncalibrated"
    assert aggregate_judges([good], [True])["winner"] is None
    assert (
        aggregate_judges([good, good], [True, True], ["gemini", "qwen"])["winner"]
        == "candidate"
    )


def test_duplicate_or_unverified_judge_families_cannot_prove_quality_win():
    good = {"status": "valid", "winner": "candidate"}
    assert aggregate_judges([good, good], [True, True])["winner"] is None
    assert (
        aggregate_judges([good, good], [True, True], ["gemini", "gemini"])["winner"]
        is None
    )


async def test_judge_costs_and_failed_calibration_are_preserved(tmp_path):
    comparison = AsyncMock(
        side_effect=[
            {"status": "valid", "winner": "candidate"},
            {"status": "valid", "winner": "baseline"},
            {"status": "valid", "winner": "candidate"},
            {"status": "valid", "winner": "candidate"},
        ]
    )
    with (
        patch("evals.evidence_ablation.wf.agent", AsyncMock(return_value="bad JSON")),
        patch("evals.evidence_ablation.compare_answers", comparison),
    ):
        report = await run(
            tmp_path / "evidence.json",
            ["google:test"],
            ["google:judge", "openai:judge"],
            ["gemini", "other"],
            count=1,
            allowance=2,
            arms=("single", "self_refine"),
        )
    assert len(report["rows"]) == 2
    assert all(not row["grounded"] for row in report["rows"])
    evaluated = next(row for row in report["rows"] if row["arm"] == "self_refine")
    assert evaluated["comparison"]["status"] == "grounding_failed"
    assert evaluated["comparison"]["winner"] is None
    assert len(evaluated["judges"]) == 2
    assert len(report["calibration"]) == 2
    assert not report["calibration"][1]["passed"]
    assert json.loads((tmp_path / "evidence.json").read_text()) == report


async def test_failed_grounding_cannot_be_a_valid_quality_win(tmp_path):
    comparison = AsyncMock(return_value={"status": "valid", "winner": "candidate"})
    with (
        patch("evals.evidence_ablation.wf.agent", AsyncMock(return_value="bad JSON")),
        patch("evals.evidence_ablation.compare_answers", comparison),
    ):
        report = await run(
            tmp_path / "failed.json",
            ["google:test"],
            ["google:judge", "openai:judge"],
            ["gemini", "qwen"],
            count=1,
            allowance=2,
            arms=("single", "self_refine"),
        )
    row = next(row for row in report["rows"] if row["arm"] == "self_refine")
    assert row["comparison"] == {"status": "grounding_failed", "winner": None}


def test_runtime_identity_does_not_trust_declared_alias_families():
    assert recorded_family([{"model": "openai/qwen3.8-flash"}]) == "qwen"
    assert recorded_family([{"model": "gemini-3.5-flash"}]) == "gemini"
    assert recorded_family([{"model": "openai/custom-alias"}]) is None
    assert recorded_family([]) is None
    assert (
        recorded_family(
            [{"model": "openai/qwen3.8-flash"}, {"model": "gemini-3.5-flash"}]
        )
        is None
    )


async def test_each_roster_model_has_a_one_call_baseline():
    calls = AsyncMock(return_value="answer")
    with patch("evals.evidence_ablation.wf.agent", calls):
        await generate("problem", ["google:first", "openai:second"], "single_1", 3)
    assert calls.await_count == 1
    assert calls.await_args.kwargs["model"] == "openai:second"


async def test_roster_controls_are_generated_and_compared_separately(tmp_path):
    comparison = AsyncMock(return_value={"status": "valid", "winner": "candidate"})
    with (
        patch("evals.evidence_ablation.wf.agent", AsyncMock(return_value="bad JSON")),
        patch("evals.evidence_ablation.compare_answers", comparison),
    ):
        report = await run(
            tmp_path / "roster.json",
            ["google:first", "openai:second"],
            ["google:judge", "openai:judge"],
            ["gemini", "qwen"],
            count=1,
            allowance=1,
            arms=("single", "self_refine"),
        )
    assert {row["arm"] for row in report["rows"]} == {
        "single",
        "single_1",
        "self_refine",
    }
    row = next(row for row in report["rows"] if row["arm"] == "self_refine")
    assert set(row["comparisons_by_baseline"]) == {"single", "single_1"}
    assert len(row["judges"]) == 4
    assert comparison.await_count == 6


async def test_predeclaration_precedes_calibration(tmp_path):
    output = tmp_path / "before-calibration.json"

    async def checked_judge(*args, **kwargs):
        protocol = json.loads(output.with_suffix(".protocol.json").read_text())
        assert protocol["configuration"]["judges"] == ["google:judge", "openai:judge"]
        assert protocol["source_digests"]["evals/evidence_eval.py"]
        assert json.loads(output.read_text())["rows"] == []
        return {"status": "valid", "winner": "candidate"}

    with (
        patch(
            "evals.evidence_ablation.compare_answers",
            AsyncMock(side_effect=checked_judge),
        ),
        patch("evals.evidence_ablation.wf.agent", AsyncMock(return_value="bad JSON")),
    ):
        report = await run(
            output,
            ["google:test"],
            ["google:judge", "openai:judge"],
            ["gemini", "qwen"],
            count=1,
            allowance=1,
            arms=("single",),
        )
    assert all(entry["receipt"]["error"] is None for entry in report["calibration"])
