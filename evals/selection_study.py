"""Development study: deployable final selection over self-refinement trajectories.

Question: held-out diagnostics found correct intermediate answers in 19-21/24
self-refinement trials but only 8-10/24 correct final answers. Which oracle-free
selection rule recovers them? One trajectory is generated per trial; every rule
selects from the *same saved candidates*, so differences isolate selection from
generation. The hidden optimum is used only afterwards, by the evaluator.

Development split only (``dev`` seeds): never tune on the frozen held-out pool.
Rules cost nothing except ``llm_pick``, which adds one metered workflow step.
Allowance counts workflow agent steps, not provider requests, tokens or dollars.
"""

import argparse
import asyncio
import json
from pathlib import Path

from dialectica import Workflow
from dialectica import workflow as wf
from dialectica.json_repair import strip_code_fence
from evals.experiment_protocol import freeze_protocol
from evals.measurement import measure_arm, observe_runtime
from evals.meta_ablation import prediction_key
from evals.research_tasks import make_portfolio_tasks
from evals.selection_rules import RULES, selector_indices

ALL_RULES = (*RULES, "llm_pick")


async def trajectory(problem: str, models: list[str], steps: int) -> list[str]:
    """Same self-refine loop as ``meta_ablation`` (first answer == single call)."""
    answers: list[str] = []
    for index in range(steps):
        context = ""
        if answers:
            context = (
                f"\nPREVIOUS ANSWER:\n{answers[-1]}\n"
                "Independently check every constraint and arithmetic step. "
                "Correct any flaw and retain a correct answer."
            )
        answers.append(
            await wf.agent(
                problem + context + "\nSolve carefully and return a complete answer "
                "in the task's required format.",
                model=models[index % len(models)],
                label=f"self_refine-{index}",
                sees=[],
                max_attempts=1,
            )
        )
    return answers


async def llm_pick(problem: str, answers: list[str], model: str) -> int | None:
    """One extra step: choose among distinct candidates, with no oracle access."""
    distinct: list[int] = []
    seen: set[tuple[int, ...]] = set()
    for index, answer in enumerate(answers):
        try:
            key = prediction_key(answer, "portfolio")
        except ValueError:
            continue
        if key not in seen:
            seen.add(key)
            distinct.append(index)
    if not distinct:
        return None
    if len(distinct) == 1:
        return distinct[0]
    listing = "\n".join(f"[{n}] {answers[i]}" for n, i in enumerate(distinct))
    raw = await wf.agent(
        f"{problem}\n\nCandidate answers (distinct):\n{listing}\n\n"
        "Verify each candidate against every constraint, then pick the one that is "
        'feasible and has the highest total reward. Return only {"choice": <number>}.',
        model=model,
        label="llm_pick",
        sees=[],
        max_attempts=1,
    )
    try:
        choice = json.loads(strip_code_fence(raw))["choice"]
        return (
            distinct[choice]
            if type(choice) is int and 0 <= choice < len(distinct)
            else None
        )
    except (ValueError, TypeError, KeyError):
        return None


def summarize(rows: list[dict], rules: tuple[str, ...] = ALL_RULES) -> dict:
    """Paired counts per rule; unparseable/absent selections count as failures."""
    ok = [row for row in rows if row.get("error") is None]
    summary: dict = {
        "trials": len(rows),
        "completed": len(ok),
        "coverage": sum(1 for row in ok if row["coverage"]),
        "rules": {},
    }
    for rule in rules:
        stats = {"passed": 0, "rescued_vs_last": 0, "harmed_vs_last": 0, "none": 0}
        calls = []
        for row in ok:
            chosen = row["selected"].get(rule)
            if rule not in row["selected"]:
                continue
            passed = chosen is not None and row["passed"][chosen]
            last = row["passed"][len(row["passed"]) - 1]
            stats["passed"] += int(passed)
            stats["none"] += int(chosen is None)
            stats["rescued_vs_last"] += int(passed and not last)
            stats["harmed_vs_last"] += int(last and not passed)
            if chosen is not None and rule == "convergence":
                calls.append(chosen + 1)
        if rule == "convergence" and calls:
            stats["mean_steps_if_stopped_at_selection"] = sum(calls) / len(calls)
        summary["rules"][rule] = stats
    return summary


async def run(
    output: Path,
    models: list[str],
    count: int = 8,
    difficulty: int = 8,
    steps: int = 8,
    repeats: int = 1,
    pick: bool = False,
    split: str = "dev",
) -> dict:
    if split != "dev":
        raise ValueError("selection rules are developed on the dev split only")
    if not models or steps < 2 or repeats < 1:
        raise ValueError("models, steps >= 2 and repeats >= 1 required")
    tasks = make_portfolio_tasks(split, count=count, size=difficulty)
    report = {
        "protocol": "selection-study-v1",
        "split": split,
        "count": count,
        "family": "portfolio",
        "difficulty": difficulty,
        "models": models,
        "steps": steps,
        "repeats": repeats,
        "llm_pick": pick,
        "rules": list(ALL_RULES if pick else RULES),
        "allowance_unit": "workflow_agent_steps",
        "token_parity": False,
        "dollar_parity": False,
        "oracle_access": "evaluation only",
        "rows": [],
    }
    freeze_protocol(output, report, tasks)
    with observe_runtime():
        for task in tasks:
            for repeat in range(repeats):

                async def script(statement=task.statement):
                    return await trajectory(statement, models, steps)

                receipt = await measure_arm(
                    "trajectory",
                    lambda: Workflow(script, budget_total=steps).run(),
                )
                row: dict = {
                    "task_id": task.task_id,
                    "repeat": repeat,
                    "error": receipt.error,
                    "trajectory_receipt": receipt.to_dict(),
                }
                if receipt.error is None:
                    answers = receipt.output
                    row["answers"] = answers
                    row["passed"] = [task.verify_content(a)[0] for a in answers]
                    row["coverage"] = any(row["passed"])
                    row["selected"] = selector_indices(answers, task)
                    if pick:

                        async def pick_script(
                            statement=task.statement, candidates=answers
                        ):
                            return await llm_pick(statement, candidates, models[-1])

                        pick_receipt = await measure_arm(
                            "llm_pick",
                            lambda: Workflow(pick_script, budget_total=1).run(),
                        )
                        row["pick_receipt"] = pick_receipt.to_dict()
                        row["selected"]["llm_pick"] = (
                            pick_receipt.output if pick_receipt.error is None else None
                        )
                report["rows"].append(row)
                output.write_text(json.dumps(report, indent=2))
                print(
                    json.dumps(
                        {
                            "task": task.task_id,
                            "repeat": repeat,
                            "error": receipt.error,
                            "coverage": row.get("coverage"),
                            "passed": row.get("passed"),
                            "selected": row.get("selected"),
                            "tokens": receipt.usage.total_tokens,
                        }
                    ),
                    flush=True,
                )
    report["summary"] = summarize(report["rows"], tuple(report["rules"]))
    output.write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--difficulty", type=int, default=8)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--llm-pick", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(
        run(
            args.output,
            args.models,
            args.count,
            args.difficulty,
            args.steps,
            args.repeats,
            args.llm_pick,
        )
    )
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
