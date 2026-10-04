"""Evidence-grounded decisions with separately metered, calibrated judges.

Calibration checks an obvious factual violation, not general judge accuracy.
The nominal allowance counts workflow agent steps; underlying SDK retries can
make more provider requests. Token and dollar parity are not implied.
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from dialectica import Workflow
from dialectica import workflow as wf
from evals.evidence_eval import compare_answers
from evals.evidence_tasks import make_evidence_tasks
from evals.experiment_protocol import freeze_protocol
from evals.measurement import measure_arm, observe_runtime
from examples.patterns.meta_reasoning_pattern import create_meta_reasoning_engine
from examples.patterns.reflection_pattern import create_reflection_engine

ARMS = (
    "single",
    "self_refine",
    "reflection_homo",
    "reflection_hetero",
    "staged",
    "direct",
)
CALIBRATION_TASK = (
    "Synthetic case: Budget is 100 thousand dollars. Sensitive customer records "
    "cannot be sent to an unapproved vendor. Vendor approval has not been granted. "
    "A two-week synthetic-data evaluation costs 1 thousand dollars. Decide the "
    "next action with a measurable trigger; factual feasibility is mandatory."
)
CALIBRATION_GOOD = (
    "Run the two-week synthetic-data evaluation for 1 thousand dollars. Keep "
    "customer records internal. Consider production only after documented security "
    "approval and a measured workload test; evaluation alone does not establish "
    "production compliance. Stop at the authorized evaluation spend."
)
CALIBRATION_BAD = (
    "Immediately send all sensitive customer records to the unapproved vendor. "
    "Spend 500 thousand dollars now. The source confirms vendor approval and a "
    "budget of 500 thousand dollars, so no further checks are needed."
)


def aggregate_judges(
    results: list[dict],
    calibrated: list[bool],
    families: list[str | None] | None = None,
) -> dict:
    """A quality verdict requires at least two calibrated agreeing judges."""
    if len(results) < 2 or len(calibrated) != len(results) or not all(calibrated):
        return {"status": "uncalibrated", "winner": None}
    if (
        not families
        or len(families) != len(results)
        or any(family is None for family in families)
        or len(set(families)) != len(families)
    ):
        return {"status": "independence_unverified", "winner": None}
    if any(result.get("status") != "valid" for result in results):
        return {"status": "inconclusive", "winner": None}
    winners = {result.get("winner") for result in results}
    if len(winners) != 1 or not winners <= {"candidate", "baseline", "tie"}:
        return {"status": "judge_disagreement", "winner": None}
    return {"status": "valid", "winner": winners.pop()}


def recorded_family(records: list[dict]) -> str | None:
    """Check requested runtime model identity; provider-internal routing is opaque."""
    names = {record.get("model") for record in records}
    if len(names) != 1 or not all(isinstance(name, str) for name in names):
        return None
    name = names.pop().lower().rsplit("/", 1)[-1]
    for prefix, family in (
        ("gemini", "gemini"),
        ("qwen", "qwen"),
        ("glm", "glm"),
        ("gpt", "openai"),
        ("claude", "anthropic"),
    ):
        if name.startswith(prefix):
            return family
    return None


async def generate(problem: str, models: list[str], arm: str, allowance: int) -> dict:
    if arm.startswith("reflection_"):
        roster = models if arm == "reflection_hetero" else [models[0]]
        return await create_reflection_engine(problem, roster=roster).run()
    if arm in {"staged", "direct"}:
        return await create_meta_reasoning_engine(
            problem,
            workers=models,
            controller_model=models[0],
            mode=arm,
            max_calls=allowance,
        ).run()
    previous = ""
    single_index = (
        0
        if arm == "single"
        else int(arm.removeprefix("single_"))
        if arm.startswith("single_")
        else None
    )
    for index in range(1 if single_index is not None else allowance):
        context = (
            f"\nPREVIOUS ANSWER:\n{previous}\nCheck factual support, feasibility "
            "and the strongest competing option. Correct flaws; retain sound decisions."
            if previous
            else ""
        )
        previous = await wf.agent(
            problem + context,
            model=models[
                single_index if single_index is not None else index % len(models)
            ],
            label=f"{arm}-{index}",
            sees=[],
            max_attempts=1,
        )
    return {"final_answer": previous}


async def run(
    output: Path,
    models: list[str],
    judges: list[str],
    judge_families: list[str],
    split: str = "dev",
    count: int = 4,
    allowance: int = 12,
    repeats: int = 1,
    arms: tuple[str, ...] = ARMS,
    order_seed: int = 10427,
) -> dict:
    if (
        not models
        or len(judges) < 2
        or len(judges) != len(judge_families)
        or len(set(judges)) != len(judges)
        or len(set(judge_families)) != len(judges)
        or not all(judge_families)
        or allowance < 1
        or repeats < 1
        or "single" not in arms
        or len(set(arms)) != len(arms)
        or any(arm not in ARMS for arm in arms)
    ):
        raise ValueError("valid arms and at least two distinct judge families required")
    if any(arm.startswith("reflection_") for arm in arms) and allowance < 10:
        raise ValueError("reflection requires at least ten workflow steps")
    if "reflection_hetero" in arms and len(set(models)) < 2:
        raise ValueError("heterogeneous reflection requires distinct models")
    tasks = make_evidence_tasks(split, count)
    baseline_models = {
        "single": models[0],
        **{f"single_{index}": model for index, model in enumerate(models[1:], 1)},
    }
    expanded_arms = (*arms, *list(baseline_models)[1:])
    report = {
        "protocol": "evidence-ablation-v3",
        "split": split,
        "count": count,
        "models": models,
        "judges": judges,
        "judge_families_declared": judge_families,
        "allowance": allowance,
        "allowance_unit": "workflow_agent_steps",
        "token_parity": False,
        "dollar_parity": False,
        "repeats": repeats,
        "requested_arms": list(arms),
        "arms": list(expanded_arms),
        "baseline_models": baseline_models,
        "order_seed": order_seed,
        "calibration_scope": "obvious factual violation only",
        "grounding_scope": "quote identity and output structure, not decision quality",
        "calibration": [],
        "rows": [],
    }
    freeze_protocol(output, report, tasks)

    def save() -> None:
        output.write_text(json.dumps(report, indent=2))

    async def judged(problem: str, candidate: str, baseline: str, model: str):
        return await measure_arm(
            "judge",
            lambda: Workflow(
                lambda: compare_answers(problem, candidate, baseline, model),
                budget_total=2,
            ).run(),
        )

    rng = random.Random(order_seed)
    with observe_runtime():
        for model in judges:
            receipt = await judged(
                CALIBRATION_TASK, CALIBRATION_GOOD, CALIBRATION_BAD, model
            )
            result = receipt.output if receipt.error is None else {}
            passed = (
                result.get("status") == "valid" and result.get("winner") == "candidate"
            )
            report["calibration"].append(
                {"model": model, "passed": passed, "receipt": receipt.to_dict()}
            )
            save()
        calibrated = [entry["passed"] for entry in report["calibration"]]
        families = []
        for entry, declared in zip(report["calibration"], judge_families):
            family = recorded_family(entry["receipt"]["records"])
            entry["recorded_family"] = family
            entry["family_matches_declaration"] = family == declared.lower()
            families.append(family if family == declared.lower() else None)
        save()
        for task in tasks:
            for repeat in range(repeats):
                order = list(expanded_arms)
                rng.shuffle(order)
                rows = []
                for arm in order:
                    receipt = await measure_arm(
                        arm,
                        lambda arm=arm, problem=task.statement: Workflow(
                            lambda: generate(problem, models, arm, allowance),
                            budget_total=allowance,
                        ).run(),
                    )
                    row = {
                        "task_id": task.task_id,
                        "task": task.statement,
                        "sources": task.sources,
                        "question": task.question,
                        "repeat": repeat,
                        "arm": arm,
                        "order": order,
                        "receipt": receipt.to_dict(),
                        "grounded": None,
                        "judges": [],
                        "comparison": None,
                        "comparisons_by_baseline": {},
                    }
                    if receipt.error is None:
                        row["grounded"], row["grounding_feedback"] = (
                            task.verify_content(receipt.output["final_answer"])
                        )
                    rows.append(row)
                    report["rows"].append(row)
                    save()
                baselines = [row for row in rows if row["arm"] in baseline_models]
                for row in rows:
                    if row["arm"] in baseline_models:
                        continue
                    for baseline in baselines:
                        key = baseline["arm"]
                        if row["receipt"]["error"] or baseline["receipt"]["error"]:
                            comparison = {"status": "generation_failed", "winner": None}
                        else:
                            results, comparison_families = [], []
                            for model in judges:
                                receipt = await judged(
                                    task.statement,
                                    row["receipt"]["output"]["final_answer"],
                                    baseline["receipt"]["output"]["final_answer"],
                                    model,
                                )
                                row["judges"].append(
                                    {
                                        "model": model,
                                        "baseline_arm": key,
                                        "receipt": receipt.to_dict(),
                                    }
                                )
                                results.append(
                                    receipt.output
                                    if receipt.error is None
                                    else {"status": "measurement_failed"}
                                )
                                comparison_families.append(
                                    recorded_family(receipt.records)
                                )
                                save()
                            verified_families = [
                                family if family == observed else None
                                for family, observed in zip(
                                    families, comparison_families
                                )
                            ]
                            comparison = (
                                {"status": "grounding_failed", "winner": None}
                                if not row["grounded"] or not baseline["grounded"]
                                else aggregate_judges(
                                    results, calibrated, verified_families
                                )
                            )
                        row["comparisons_by_baseline"][key] = comparison
                        if key == "single":
                            row["comparison"] = comparison
                        save()
                print(
                    json.dumps(
                        {
                            "task": task.task_id,
                            "repeat": repeat,
                            "grounded": {row["arm"]: row["grounded"] for row in rows},
                            "comparisons": {
                                row["arm"]: row["comparison"] for row in rows
                            },
                        }
                    ),
                    flush=True,
                )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--judges", nargs="+", required=True)
    parser.add_argument("--judge-families", nargs="+", required=True)
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--allowance", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--order-seed", type=int, default=10427)
    args = parser.parse_args()
    asyncio.run(
        run(
            args.output,
            args.models,
            args.judges,
            args.judge_families,
            args.split,
            args.count,
            args.allowance,
            args.repeats,
            tuple(args.arms),
            args.order_seed,
        )
    )


if __name__ == "__main__":
    main()
