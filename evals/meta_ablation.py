"""Verifier-backed artifact-control experiment with randomized arm order.

All multi-call arms have the same nominal allowance and model roster. Report
realized workflow steps/tokens, never claim dollar or token parity from that allowance.
SDK retries and tool turns can cause extra provider requests within one step.
Only the evaluator sees the oracle. Development runs are not held-out evidence.
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from dialectica import Workflow
from dialectica import workflow as wf
from dialectica.json_repair import strip_code_fence
from evals.experiment_protocol import freeze_protocol
from evals.measurement import measure_arm, observe_runtime
from evals.research_tasks import make_portfolio_tasks, make_state_tasks
from examples.patterns.meta_reasoning_pattern import create_meta_reasoning_engine

ARMS = ("single", "consensus", "self_refine", "staged", "direct")


def prediction_key(answer: str, family: str) -> tuple[int, ...]:
    try:
        payload = json.loads(strip_code_fence(answer))
        values = payload["selected" if family == "portfolio" else "state"]
        if isinstance(values, list) and all(type(value) is int for value in values):
            return tuple(sorted(values)) if family == "portfolio" else tuple(values)
    except (ValueError, TypeError, KeyError):
        pass
    raise ValueError("unparseable task prediction")


async def sampling(
    problem: str, models: list[str], arm: str, allowance: int, family: str
) -> dict:
    answers = []
    for index in range(1 if arm == "single" else allowance):
        context = ""
        if arm == "self_refine" and answers:
            context = (
                f"\nPREVIOUS ANSWER:\n{answers[-1]}\nIndependently check every constraint "
                "and arithmetic step. Correct any flaw and retain a correct answer."
            )
        answer = await wf.agent(
            problem + context + "\nSolve carefully and return a complete answer "
            "in the task's required format.",
            model=models[index % len(models)],
            label=f"{arm}-{index}",
            sees=[],
            max_attempts=1,
        )
        answers.append(answer)
    selected = answers[-1]
    if arm == "consensus":
        counts = {}
        representatives = {}
        for answer in answers:
            try:
                key = prediction_key(answer, family)
            except ValueError:
                continue
            counts[key] = counts.get(key, 0) + 1
            representatives.setdefault(key, answer)
        if not counts:
            raise ValueError("no parsed sampling predictions")
        selected = representatives[max(counts, key=counts.__getitem__)]
    return {
        "final_answer": selected,
        "artifacts": [{"answer": answer} for answer in answers],
    }


async def run(
    output: Path,
    models: list[str],
    split: str = "dev",
    count: int = 4,
    family: str = "portfolio",
    difficulty: int = 8,
    allowance: int = 12,
    repeats: int = 1,
    arms: tuple[str, ...] = ARMS,
    order_seed: int = 10426,
) -> dict:
    if (
        not models
        or allowance < 1
        or repeats < 1
        or not arms
        or any(arm not in ARMS for arm in arms)
    ):
        raise ValueError("valid models, allowance, repeats and arms required")
    if family not in {"portfolio", "state"}:
        raise ValueError("unknown task family")
    tasks = (
        make_portfolio_tasks(split, count=count, size=difficulty)
        if family == "portfolio"
        else make_state_tasks(split, count=count, steps=difficulty)
    )
    report = {
        "protocol": "meta-ablation-v1",
        "split": split,
        "count": count,
        "family": family,
        "difficulty": difficulty,
        "models": models,
        "allowance": allowance,
        "allowance_unit": "workflow_agent_steps",
        "token_parity": False,
        "dollar_parity": False,
        "repeats": repeats,
        "arms": list(arms),
        "order_seed": order_seed,
        "oracle_access": "evaluation only",
        "rows": [],
    }
    freeze_protocol(output, report, tasks)
    rng = random.Random(order_seed)
    with observe_runtime():
        for task in tasks:
            for repeat in range(repeats):
                order = list(arms)
                rng.shuffle(order)
                for arm in order:

                    async def script(problem=task.statement, selected_arm=arm):
                        if selected_arm in {"staged", "direct"}:
                            return await create_meta_reasoning_engine(
                                problem,
                                workers=models,
                                controller_model=models[0],
                                mode=selected_arm,
                                max_calls=allowance,
                            ).run()
                        return await sampling(
                            problem, models, selected_arm, allowance, family
                        )

                    receipt = await measure_arm(
                        arm, lambda: Workflow(script, budget_total=allowance).run()
                    )
                    row = {
                        "task_id": task.task_id,
                        "repeat": repeat,
                        "arm": arm,
                        "order": order,
                        "receipt": receipt.to_dict(),
                        "passed": None,
                    }
                    if receipt.error is None:
                        result = receipt.output
                        row["passed"], row["feedback"] = task.verify_content(
                            result["final_answer"]
                        )
                        row["strict_passed"] = task.verify(result["final_answer"])[0]
                        row["coverage"] = any(
                            task.verify_content(artifact["answer"])[0]
                            for artifact in result["artifacts"]
                        )
                    report["rows"].append(row)
                    output.write_text(json.dumps(report, indent=2))
                    print(
                        json.dumps(
                            {
                                "task": task.task_id,
                                "repeat": repeat,
                                "arm": arm,
                                "passed": row["passed"],
                                "error": receipt.error,
                                "calls": receipt.calls,
                                "tokens": receipt.usage.total_tokens,
                            }
                        ),
                        flush=True,
                    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--family", choices=["portfolio", "state"], default="portfolio")
    parser.add_argument("--difficulty", type=int, default=8)
    parser.add_argument("--allowance", type=int, default=12)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--order-seed", type=int, default=10426)
    args = parser.parse_args()
    asyncio.run(
        run(
            args.output,
            args.models,
            args.split,
            args.count,
            args.family,
            args.difficulty,
            args.allowance,
            args.repeats,
            tuple(args.arms),
            args.order_seed,
        )
    )


if __name__ == "__main__":
    main()
