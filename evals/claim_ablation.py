"""Development/held-out CLR mechanism comparison with workflow-step and token receipts.

All arms use the same task and answer/claim schema. Consensus gets 2K generation
workflow steps, CLR gets K generation + K assessment steps; self-refine gets
2K sequential steps. This is not provider-request, token or dollar parity. The hidden
oracle is used only after selection, never supplied to an arm. A same-candidate
unweighted selection diagnoses selection improvement separately from coverage.
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from dialectica import workflow as wf
from dialectica.json_repair import strip_code_fence
from dialectica.workflow import Workflow
from evals.experiment_protocol import freeze_protocol
from evals.measurement import measure_arm, observe_runtime
from evals.research_tasks import make_portfolio_tasks
from examples.patterns.claim_falsification_pattern import (
    ClaimCandidate,
    ClaimVerdicts,
    create_claim_falsification_engine,
    select_candidate,
)

ARMS = ("single", "consensus", "self_refine", "claims")


def answer_key(answer: str) -> str:
    try:
        payload = json.loads(strip_code_fence(answer))
        selected = payload["selected"]
        if isinstance(selected, list) and all(type(i) is int for i in selected):
            return json.dumps(sorted(selected))
    except (ValueError, TypeError, KeyError):
        pass
    raise ValueError("unparseable portfolio prediction")


async def baseline(problem: str, model: str, arm: str, samples: int) -> dict:
    candidates = []
    calls = 1 if arm == "single" else 2 * samples
    for index in range(calls):
        context = ""
        if arm == "self_refine" and candidates:
            context = (
                "\nPrevious attempt:\n"
                + candidates[-1].model_dump_json()
                + "\nIndependently check all constraints and global optimality. "
                "Correct any flaw; retain a correct answer."
            )
        candidate = await wf.agent(
            problem
            + context
            + "\nSolve carefully. Put the final task answer in answer. "
            "Include exactly five concise decision-critical claims whose failure "
            "would undermine the answer; omit routine summaries and answer restatements.",
            schema=ClaimCandidate,
            model=model,
            label=f"{arm}-{index}",
            sees=[],
            max_attempts=1,
        )
        if not isinstance(candidate, ClaimCandidate):
            raise TypeError("invalid baseline candidate measurement")
        candidates.append(candidate)
    answer = (
        candidates[-1].answer
        if arm == "self_refine"
        else select_candidate(
            candidates,
            [ClaimVerdicts(survived=[True] * 5)] * len(candidates),
            answer_key,
        )
    )
    return {"final_answer": answer, "candidates": [c.model_dump() for c in candidates]}


async def run(
    output: Path,
    models: list[str],
    split: str,
    count: int,
    size: int,
    samples: int = 2,
    repeats: int = 1,
    arms: tuple[str, ...] = ARMS,
    order_seed: int = 10431,
) -> dict:
    if (
        not models
        or len(set(models)) != len(models)
        or type(samples) is not int
        or samples < 1
        or type(repeats) is not int
        or repeats < 1
        or not arms
        or len(set(arms)) != len(arms)
        or any(arm not in ARMS for arm in arms)
    ):
        raise ValueError(
            "valid unique models/arms and positive samples/repeats required"
        )
    report = {
        "protocol": "claim-ablation-v3",
        "count": count,
        "arms": list(arms),
        "order_seed": order_seed,
        "allowance": 2 * samples,
        "allowance_unit": "workflow_agent_steps",
        "token_parity": False,
        "dollar_parity": False,
        "split": split,
        "size": size,
        "models": models,
        "samples": samples,
        "repeats": repeats,
        "oracle_access": "evaluation only",
        "rows": [],
    }
    tasks = make_portfolio_tasks(split, count=count, size=size)
    freeze_protocol(output, report, tasks)
    rng = random.Random(order_seed)
    with observe_runtime():
        for task in tasks:
            for model in models:
                for repeat in range(repeats):
                    order = list(arms)
                    rng.shuffle(order)
                    for arm in order:

                        async def script(
                            problem=task.statement,
                            selected_model=model,
                            selected_arm=arm,
                        ):
                            if selected_arm == "claims":
                                return await create_claim_falsification_engine(
                                    problem,
                                    model=selected_model,
                                    samples=samples,
                                    answer_key=answer_key,
                                ).run()
                            return await baseline(
                                problem, selected_model, selected_arm, samples
                            )

                        receipt = await measure_arm(
                            arm,
                            lambda: Workflow(script, budget_total=2 * samples).run(),
                        )
                        row = {
                            "task_id": task.task_id,
                            "model": model,
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
                            row["strict_passed"] = task.verify(result["final_answer"])[
                                0
                            ]
                            row["coverage"] = any(
                                task.verify_content(c["answer"])[0]
                                for c in result["candidates"]
                            )
                            if arm == "claims":
                                candidates = [
                                    ClaimCandidate.model_validate(c)
                                    for c in result["candidates"]
                                ]
                                unweighted = select_candidate(
                                    candidates,
                                    [ClaimVerdicts(survived=[True] * 5)]
                                    * len(candidates),
                                    answer_key,
                                )
                                row["same_candidate_consensus_passed"] = (
                                    task.verify_content(unweighted)[0]
                                )
                        report["rows"].append(row)
                        output.write_text(json.dumps(report, indent=2))
                        print(
                            json.dumps(
                                {
                                    k: row[k]
                                    for k in (
                                        "task_id",
                                        "model",
                                        "repeat",
                                        "arm",
                                        "passed",
                                    )
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
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--size", type=int, default=14)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--order-seed", type=int, default=10431)
    args = parser.parse_args()
    asyncio.run(
        run(
            args.output,
            args.models,
            args.split,
            args.count,
            args.size,
            args.samples,
            args.repeats,
            tuple(args.arms),
            args.order_seed,
        )
    )


if __name__ == "__main__":
    main()
