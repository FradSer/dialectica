"""Task-cluster uncertainty bounds for evidence-panel preferences.

Unmeasured preferences range from -1 to +1; they are never inserted as quality
ties. Panel agreement is not human alignment. All intervals are exploratory.
"""

import argparse
import json
import random
from collections import Counter
from math import isfinite
from pathlib import Path
from statistics import mean

from evals.experiment_protocol import EVIDENCE_ANALYSIS_RULES, load_frozen_report
from evals.objective_analysis import bootstrap


def summarize_cost(receipts: list[dict]) -> dict:
    """Keep generation, calibration and judging expenses independently metered."""
    for receipt in receipts:
        usage = receipt["usage"]
        for field in ("total_tokens", "unknown_calls", "model_calls"):
            if field == "model_calls" and field not in usage:
                continue
            if type(usage.get(field)) is not int or usage[field] < 0:
                raise ValueError("nonnegative integer usage counters required")
        if type(receipt.get("calls")) is not int or receipt["calls"] < 0:
            raise ValueError("nonnegative integer workflow calls required")
        seconds = receipt.get("seconds")
        if type(seconds) not in (float, int) or not isfinite(seconds) or seconds < 0:
            raise ValueError("finite nonnegative latency required")
    unknown = sum(receipt["usage"]["unknown_calls"] for receipt in receipts)
    return {
        "reported_tokens": sum(
            receipt["usage"]["total_tokens"] for receipt in receipts
        ),
        "unknown_calls": unknown,
        "cost_complete": unknown == 0,
        "workflow_calls": sum(receipt["calls"] for receipt in receipts),
        "model_calls": sum(receipt["usage"]["model_calls"] for receipt in receipts)
        if all("model_calls" in receipt["usage"] for receipt in receipts)
        else None,
        "seconds": sum(receipt["seconds"] for receipt in receipts),
        "failures": sum(bool(receipt["error"]) for receipt in receipts),
    }


def analyze(report: dict, *, expected_task_ids: list[str] | None = None) -> dict:
    """Bound unknown outcomes and resample tasks after averaging their repeats."""
    arms, baselines, repeats = (
        report["arms"],
        report["baseline_models"],
        report["repeats"],
    )
    if (
        not arms
        or len(set(arms)) != len(arms)
        or not baselines
        or not set(baselines) <= set(arms)
    ):
        raise ValueError("unique arms and declared baselines required")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("positive integer repeats required")
    entries = {}
    for row in report["rows"]:
        if type(row["repeat"]) is not int:
            raise ValueError("integer repeat index required")
        key = row["task_id"], row["repeat"], row["arm"]
        if key in entries:
            raise ValueError("duplicate trial")
        entries[key] = row
    tasks = sorted({key[0] for key in entries})
    if not tasks:
        raise ValueError("nonempty task pool required")
    if expected_task_ids is not None and (
        len(set(expected_task_ids)) != len(expected_task_ids)
        or set(tasks) != set(expected_task_ids)
    ):
        raise ValueError("incomplete or duplicate expected task pool")
    expected = {
        (task, repeat, arm)
        for task in tasks
        for repeat in range(repeats)
        for arm in arms
    }
    if set(entries) != expected:
        raise ValueError("incomplete paired trials")
    for row in report["rows"]:
        if row["arm"] not in baselines and set(row["comparisons_by_baseline"]) != set(
            baselines
        ):
            raise ValueError("incomplete baseline comparisons")
    result = {
        "schema": "evidence-analysis-v1",
        "bootstrap_draws": EVIDENCE_ANALYSIS_RULES["draws"],
        "seed": EVIDENCE_ANALYSIS_RULES["seed"],
        "inference_scope": "exploratory panel preference; no multiplicity correction or human alignment proof",
        "uncertainty_scope": "unknown outcomes bounded -1..+1; bootstrap conditions on observed tasks",
        "cost_scope": "reported tokens only; provider billing and hidden retries opaque",
        "costs": {
            "generation": summarize_cost([row["receipt"] for row in report["rows"]]),
            "judging": summarize_cost(
                [judge["receipt"] for row in report["rows"] for judge in row["judges"]]
            ),
            "calibration": summarize_cost(
                [entry["receipt"] for entry in report["calibration"]]
            ),
        },
        "comparisons": [],
    }
    rng = random.Random(result["seed"])
    scores = {"candidate": 1, "baseline": -1, "tie": 0}
    for arm in arms:
        if arm in baselines:
            continue
        for baseline in baselines:
            lower, upper, valid, statuses = [], [], [], Counter()
            for task in tasks:
                known, unknown = [], 0
                for repeat in range(repeats):
                    comparison = entries[task, repeat, arm]["comparisons_by_baseline"][
                        baseline
                    ]
                    if comparison["status"] not in {
                        "valid",
                        "uncalibrated",
                        "independence_unverified",
                        "inconclusive",
                        "judge_disagreement",
                        "grounding_failed",
                        "generation_failed",
                    }:
                        raise ValueError("unknown measurement status")
                    statuses[comparison["status"]] += 1
                    if comparison["status"] == "valid":
                        if comparison["winner"] not in scores:
                            raise ValueError("invalid measured preference")
                        known.append(scores[comparison["winner"]])
                        valid.append(scores[comparison["winner"]])
                    else:
                        if comparison["winner"] is not None:
                            raise ValueError(
                                "inconclusive preference cannot have a winner"
                            )
                        unknown += 1
                lower.append((sum(known) - unknown) / repeats)
                upper.append((sum(known) + unknown) / repeats)
            result["comparisons"].append(
                {
                    "arm": arm,
                    "baseline": baseline,
                    "tasks": len(tasks),
                    "trials": len(tasks) * repeats,
                    "valid_trials": len(valid),
                    "inconclusive_trials": len(tasks) * repeats - len(valid),
                    "status_counts": dict(statuses),
                    "valid_only_net_preference": mean(valid) if valid else None,
                    "identification_bounds": [mean(lower), mean(upper)],
                    "outer_interval": [
                        bootstrap(lower, result["bootstrap_draws"], rng)[0],
                        bootstrap(upper, result["bootstrap_draws"], rng)[1],
                    ],
                    "degenerate_task_bounds": len(set(lower)) == 1
                    and len(set(upper)) == 1,
                    "limitations": "valid-only mean is selected evidence; degenerate intervals do not imply certainty",
                }
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exploratory-reanalysis", action="store_true")
    args = parser.parse_args()
    report, tasks, metadata = load_frozen_report(
        args.report,
        rule_family="evidence",
        analysis_source="evals/evidence_analysis.py",
        allow_drift=args.exploratory_reanalysis,
    )
    result = analyze(report, expected_task_ids=tasks)
    result.update(metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
