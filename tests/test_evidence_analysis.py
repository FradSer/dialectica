"""Unknown panel preferences remain interval uncertainty, never imputed ties."""

import pytest

from evals.evidence_analysis import analyze


def receipt(tokens=10, unknown=0):
    return {
        "calls": 1,
        "seconds": 1,
        "error": None,
        "usage": {"total_tokens": tokens, "unknown_calls": unknown, "model_calls": 1},
    }


def report_with_comparisons(comparisons):
    rows = []
    for index, comparison in enumerate(comparisons):
        for arm in ("single", "self_refine"):
            rows.append(
                {
                    "task_id": f"task-{index // 2}",
                    "repeat": index % 2,
                    "arm": arm,
                    "receipt": receipt(),
                    "judges": [{"receipt": receipt()}] if arm != "single" else [],
                    "comparisons_by_baseline": {"single": comparison}
                    if arm != "single"
                    else {},
                }
            )
    return {
        "arms": ["single", "self_refine"],
        "baseline_models": {"single": "m1"},
        "repeats": 2,
        "rows": rows,
        "calibration": [{"receipt": receipt(20)}],
    }


def test_unknown_preferences_produce_bounds_and_costs_stay_separate():
    report = report_with_comparisons(
        [
            {"status": "valid", "winner": "candidate"},
            {"status": "judge_disagreement", "winner": None},
            {"status": "valid", "winner": "baseline"},
            {"status": "valid", "winner": "tie"},
        ]
    )
    report["rows"][3]["receipt"]["usage"]["unknown_calls"] = 1
    result = analyze(report)
    pair = result["comparisons"][0]
    assert pair["valid_trials"] == 3 and pair["inconclusive_trials"] == 1
    assert pair["identification_bounds"] == [-0.25, 0.25]
    assert pair["valid_only_net_preference"] == 0
    assert pair["outer_interval"][0] < 0 < pair["outer_interval"][1]
    assert result["costs"]["generation"]["reported_tokens"] == 80
    assert not result["costs"]["generation"]["cost_complete"]
    assert result["costs"]["judging"]["reported_tokens"] == 40
    assert result["costs"]["calibration"]["reported_tokens"] == 20


def test_all_inconclusive_has_no_quality_point_estimate():
    report = report_with_comparisons([{"status": "inconclusive", "winner": None}] * 4)
    pair = analyze(report)["comparisons"][0]
    assert pair["valid_only_net_preference"] is None
    assert pair["identification_bounds"] == [-1, 1]
    assert pair["outer_interval"] == [-1, 1]


def test_missing_trials_or_baseline_comparisons_fail():
    report = report_with_comparisons([{"status": "valid", "winner": "tie"}] * 4)
    report["rows"].pop()
    with pytest.raises(ValueError, match="incomplete"):
        analyze(report)
    report = report_with_comparisons([{"status": "valid", "winner": "tie"}] * 4)
    report["rows"][1]["comparisons_by_baseline"] = {}
    with pytest.raises(ValueError, match="baseline"):
        analyze(report)


def test_unknown_measurement_status_is_not_silent_uncertainty():
    report = report_with_comparisons([{"status": "banana", "winner": None}] * 4)
    with pytest.raises(ValueError, match="status"):
        analyze(report)
