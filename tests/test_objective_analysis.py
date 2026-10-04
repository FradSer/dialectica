"""Task-level uncertainty must not turn repeated calls into independent tasks."""

import pytest

from evals.objective_analysis import analyze


def row(task, arm, repeat, passed, error=None, unknown=0):
    return {
        "task_id": task,
        "arm": arm,
        "repeat": repeat,
        "passed": passed,
        "receipt": {
            "error": error,
            "calls": 1,
            "seconds": 2,
            "usage": {"total_tokens": 10, "unknown_calls": unknown, "model_calls": 1},
        },
    }


def test_paired_clusters_failures_and_unknown_cost_are_preserved():
    rows = []
    for repeat in range(3):
        rows.extend(
            [
                row("a", "single", repeat, False),
                row("a", "staged", repeat, True),
                row("b", "single", repeat, True),
                row("b", "staged", repeat, None, "RateLimitError", 1),
            ]
        )
    result = analyze(
        {"split": "heldout", "repeats": 3, "arms": ["single", "staged"], "rows": rows},
        draws=100,
    )
    group = result["strata"][0]
    assert group["arms"]["staged"]["tasks"] == 2
    assert group["arms"]["staged"]["trials"] == 6
    assert group["arms"]["staged"]["success_rate"] == 0.5
    assert group["arms"]["staged"]["cost_complete"] is False
    assert group["arms"]["staged"]["unknown_calls"] == 3
    assert group["comparisons"][0]["delta"] == 0
    assert group["comparisons"][0]["interval"] == [-1, 1]
    assert result["inference_scope"] == "exploratory; no multiplicity correction"


def test_missing_duplicate_and_unmeasured_outcomes_fail_analysis():
    report = {
        "repeats": 1,
        "arms": ["single", "staged"],
        "rows": [row("a", "single", 0, True)],
    }
    with pytest.raises(ValueError, match="incomplete"):
        analyze(report)
    report["rows"].append(row("a", "staged", 0, None))
    with pytest.raises(ValueError, match="unmeasured"):
        analyze(report)
    report["rows"][1]["passed"] = False
    report["rows"].append(report["rows"][0])
    with pytest.raises(ValueError, match="duplicate"):
        analyze(report)


def test_model_strata_are_separate_and_zero_variance_is_explicit():
    rows = [
        dict(row("a", "single", 0, True), model="model-a"),
        dict(row("a", "claims", 0, True), model="model-a"),
        dict(row("a", "single", 0, False), model="model-b"),
        dict(row("a", "claims", 0, True), model="model-b"),
    ]
    report = {"arms": ["single", "claims"], "repeats": 1, "rows": rows}
    result = analyze(report, draws=100)
    assert [group["comparisons"][0]["delta"] for group in result["strata"]] == [0, 1]
    assert all(
        group["comparisons"][0]["degenerate_bootstrap"] for group in result["strata"]
    )
    assert result == analyze(report, draws=100)


def test_missing_whole_task_or_declared_model_is_not_a_complete_experiment():
    rows = [dict(row("a", "single", 0, True), model="model-a")]
    report = {
        "arms": ["single"],
        "repeats": 1,
        "models": ["model-a", "model-b"],
        "rows": rows,
    }
    with pytest.raises(ValueError, match="model"):
        analyze(report)
    report["models"] = ["model-a"]
    with pytest.raises(ValueError, match="task pool"):
        analyze(report, expected_task_ids=["a", "b"])


def test_model_strata_cannot_silently_use_different_task_pools():
    report = {
        "arms": ["single"],
        "repeats": 1,
        "rows": [
            dict(row("a", "single", 0, True), model="m1"),
            dict(row("b", "single", 0, True), model="m2"),
        ],
    }
    with pytest.raises(ValueError, match="task pool"):
        analyze(report)


def test_frozen_cli_rejects_source_and_rule_drift_and_labels_reanalysis(
    tmp_path, monkeypatch
):
    import json

    from evals.experiment_protocol import digest, freeze_protocol
    from evals.objective_analysis import main
    from evals.research_tasks import make_state_tasks

    task = make_state_tasks("dev", 1, steps=2)[0]
    output = tmp_path / "run.json"
    report = {
        "split": "dev",
        "arms": ["single"],
        "repeats": 1,
        "rows": [row(task.task_id, "single", 0, True)],
    }
    freeze_protocol(output, report, [task])
    sidecar = output.with_suffix(".protocol.json")
    protocol = json.loads(sidecar.read_text())
    result_path = tmp_path / "analysis.json"
    monkeypatch.setattr(
        "sys.argv", ["analysis", str(output), "--output", str(result_path)]
    )
    main()
    saved_analysis = json.loads(result_path.read_text())
    assert saved_analysis["predeclaration_status"] == "verified"
    assert (
        saved_analysis["bootstrap_draws"]
        == protocol["analysis_rules"]["objective"]["draws"]
    )
    assert saved_analysis["seed"] == protocol["analysis_rules"]["objective"]["seed"]
    assert (
        saved_analysis["baseline"]
        == protocol["analysis_rules"]["objective"]["baseline"]
    )
    assert saved_analysis["schema"] == protocol["analysis_rules"]["objective"]["method"]
    result_path.unlink()
    protocol["source_digests"]["evals/objective_analysis.py"] = "old-source"
    sidecar.write_text(json.dumps(protocol))
    report["predeclaration_digest"] = digest(protocol)
    output.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="source"):
        main()
    assert not result_path.exists()
    monkeypatch.setattr(
        "sys.argv",
        [
            "analysis",
            str(output),
            "--output",
            str(result_path),
            "--exploratory-reanalysis",
        ],
    )
    main()
    reanalysis = json.loads(result_path.read_text())
    assert reanalysis["predeclaration_status"] == "exploratory_reanalysis"
    assert "evals/objective_analysis.py" in reanalysis["source_drift"]
    result_path.unlink()
    monkeypatch.setattr(
        "sys.argv", ["analysis", str(output), "--output", str(result_path)]
    )
    protocol["analysis_rules"]["objective"]["draws"] = 100
    sidecar.write_text(json.dumps(protocol))
    report["predeclaration_digest"] = digest(protocol)
    output.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="rules"):
        main()


@pytest.mark.parametrize(
    "field,value", [("total_tokens", -1), ("unknown_calls", True), ("model_calls", 1.5)]
)
def test_invalid_cost_counters_are_not_accepted(field, value):
    trial = row("a", "single", 0, True)
    trial["receipt"]["usage"][field] = value
    with pytest.raises(ValueError, match="usage"):
        analyze({"arms": ["single"], "repeats": 1, "rows": [trial]})


@pytest.mark.parametrize("models", [[], ["m1", "m1"]])
def test_explicit_model_declarations_are_nonempty_and_unique(models):
    report = {
        "arms": ["single"],
        "repeats": 1,
        "models": models,
        "rows": [dict(row("a", "single", 0, True), model="m1")],
    }
    with pytest.raises(ValueError, match="model"):
        analyze(report)


def test_bootstrap_draws_must_be_integer():
    with pytest.raises(ValueError, match="draws"):
        analyze(
            {"arms": ["single"], "repeats": 1, "rows": [row("a", "single", 0, True)]},
            draws=100.5,
        )
