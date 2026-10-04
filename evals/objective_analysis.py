"""Paired task-cluster bootstrap for completed objective-verifier experiments.

Repeats are averaged within tasks before resampling. Failures count against
system reliability; unknown usage remains incomplete. Intervals are exploratory,
conditional on the observed task pool, and not proof of general superiority.
"""

import argparse
import json
import random
from math import isfinite
from pathlib import Path
from statistics import mean

from evals.experiment_protocol import OBJECTIVE_ANALYSIS_RULES, load_frozen_report


def bootstrap(values: list[float], draws: int, rng: random.Random) -> list[float]:
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [samples[int((draws - 1) * 0.025)], samples[int((draws - 1) * 0.975)]]


def analyze(
    report: dict,
    *,
    baseline: str = OBJECTIVE_ANALYSIS_RULES["baseline"],
    draws: int = OBJECTIVE_ANALYSIS_RULES["draws"],
    seed: int = OBJECTIVE_ANALYSIS_RULES["seed"],
    expected_task_ids: list[str] | None = None,
) -> dict:
    """Analyze complete paired rows, separating each declared model stratum."""
    if type(draws) is not int or draws < 100 or not report.get("rows"):
        raise ValueError("at least 100 draws and nonempty rows required")
    if any("passed" not in row for row in report["rows"]):
        raise ValueError("objective outcome rows required")
    arms = report.get("arms", ["single", "consensus", "self_refine", "claims"])
    if baseline not in arms or len(set(arms)) != len(arms):
        raise ValueError("unique arms and an existing baseline required")
    repeats = report["repeats"]
    if type(repeats) is not int or repeats < 1:
        raise ValueError("positive integer repeats required")
    if expected_task_ids is not None and len(set(expected_task_ids)) != len(
        expected_task_ids
    ):
        raise ValueError("duplicate expected task IDs")
    strata: dict[str, dict] = {}
    model_fields = ["model" in row for row in report["rows"]]
    if any(model_fields) and not all(model_fields):
        raise ValueError("mixed missing and explicit model strata")
    for row in report["rows"]:
        model = row.get("model", "shared_roster")
        if not isinstance(model, str) or not model:
            raise ValueError("nonempty model stratum required")
        receipt = row["receipt"]
        usage = receipt["usage"]
        for field in ("total_tokens", "unknown_calls", "model_calls"):
            if field == "model_calls" and field not in usage:
                continue
            if type(usage.get(field)) is not int or usage[field] < 0:
                raise ValueError("nonnegative integer usage counters required")
        if type(receipt.get("calls")) is not int or receipt["calls"] < 0:
            raise ValueError("nonnegative integer workflow calls required")
        if (
            type(receipt.get("seconds")) not in (int, float)
            or not isfinite(receipt["seconds"])
            or receipt["seconds"] < 0
        ):
            raise ValueError("finite nonnegative latency required")
        if type(row["repeat"]) is not int or row["repeat"] < 0:
            raise ValueError("nonnegative integer repeat index required")
        entries = strata.setdefault(model, {})
        key = (row["task_id"], row["repeat"], row["arm"])
        if key in entries:
            raise ValueError("duplicate trial")
        passed = row["passed"]
        error = row["receipt"]["error"]
        if type(passed) is not bool and not (passed is None and error):
            raise ValueError("unmeasured objective outcome")
        if error and passed is not None:
            raise ValueError("failed generation cannot have a measured outcome")
        entries[key] = row
    if (
        any("model" in row for row in report["rows"])
        and "models" in report
        and (
            not report["models"]
            or len(set(report["models"])) != len(report["models"])
            or set(strata) != set(report["models"])
        )
    ):
        raise ValueError("incomplete declared model strata")
    result = {
        "schema": "objective-analysis-v1",
        "split": report.get("split"),
        "baseline": baseline,
        "bootstrap_draws": draws,
        "seed": seed,
        "resampling_unit": "task; repeats averaged within task",
        "inference_scope": "exploratory; no multiplicity correction",
        "failure_policy": "failed generation counts as incorrect system outcome",
        "cost_scope": "reported tokens only; provider billing and hidden retries opaque",
        "limitations": [
            "Intervals condition on this task pool, not all possible tasks.",
            "Degenerate bootstrap at a floor/ceiling does not prove certainty.",
            "Small task pools and multiple comparisons limit adoption claims.",
        ],
        "strata": [],
    }
    rng = random.Random(seed)
    common_tasks = (
        set(expected_task_ids)
        if expected_task_ids is not None
        else {key[0] for entries in strata.values() for key in entries}
    )
    for model, entries in sorted(strata.items()):
        tasks = sorted({key[0] for key in entries})
        if set(tasks) != common_tasks:
            raise ValueError("incomplete task pool")
        expected = {
            (task, repeat, arm)
            for task in tasks
            for repeat in range(repeats)
            for arm in arms
        }
        if set(entries) != expected:
            raise ValueError("incomplete or unexpected paired trials")
        group = {"model": model, "arms": {}, "comparisons": []}
        scores = {}
        for arm in arms:
            rows = [
                entries[task, repeat, arm]
                for task in tasks
                for repeat in range(repeats)
            ]
            scores[arm] = [
                mean(
                    entries[task, repeat, arm]["passed"] is True
                    for repeat in range(repeats)
                )
                for task in tasks
            ]
            usages = [row["receipt"]["usage"] for row in rows]
            unknown = sum(usage["unknown_calls"] for usage in usages)
            tokens = sum(usage["total_tokens"] for usage in usages)
            group["arms"][arm] = {
                "tasks": len(tasks),
                "trials": len(rows),
                "success_rate": mean(scores[arm]),
                "interval": bootstrap(scores[arm], draws, rng),
                "degenerate_bootstrap": len(set(scores[arm])) == 1,
                "failures": sum(bool(row["receipt"]["error"]) for row in rows),
                "reported_tokens": tokens,
                "mean_reported_tokens": tokens / len(rows),
                "unknown_calls": unknown,
                "cost_complete": unknown == 0,
                "workflow_calls": sum(row["receipt"]["calls"] for row in rows),
                "model_calls": sum(usage["model_calls"] for usage in usages)
                if all("model_calls" in usage for usage in usages)
                else None,
                "seconds": sum(row["receipt"]["seconds"] for row in rows),
            }
        for arm in arms:
            if arm == baseline:
                continue
            differences = [
                a - b for a, b in zip(scores[arm], scores[baseline], strict=True)
            ]
            group["comparisons"].append(
                {
                    "arm": arm,
                    "baseline": baseline,
                    "tasks": len(tasks),
                    "delta": mean(differences),
                    "interval": bootstrap(differences, draws, rng),
                    "degenerate_bootstrap": len(set(differences)) == 1,
                }
            )
        result["strata"].append(group)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--exploratory-reanalysis",
        action="store_true",
        help="Allow audited source/rule drift; cannot count as predeclared analysis",
    )
    args = parser.parse_args()
    report, tasks, metadata = load_frozen_report(
        args.report,
        rule_family="objective",
        analysis_source="evals/objective_analysis.py",
        allow_drift=args.exploratory_reanalysis,
    )
    result = analyze(report, expected_task_ids=tasks)
    result.update(metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
