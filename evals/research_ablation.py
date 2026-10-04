"""Live verifier-backed research pilot, with raw outputs and per-arm receipts.

Current single arm establishes whether this task family has headroom. New
methods are added only with separate acceptance tests; this pilot is not a win
claim or a reproduction of any paper benchmark.
"""

import argparse
import asyncio
import json
from pathlib import Path

from dialectica import workflow as wf
from dialectica.workflow import Workflow
from evals.measurement import measure_arm, observe_runtime
from evals.research_tasks import make_portfolio_tasks


async def run(
    output: Path, models: list[str], split: str, count: int, size: int
) -> dict:
    tasks = make_portfolio_tasks(split, count=count, size=size)
    report = {
        "protocol": "research-pilot-v1",
        "split": split,
        "size": size,
        "models": models,
        "rows": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with observe_runtime():
        for task in tasks:
            for model in models:

                async def script(prompt=task.statement, selected_model=model):
                    return await wf.agent(
                        prompt, model=selected_model, max_attempts=1, label="single"
                    )

                receipt = await measure_arm("single", lambda: Workflow(script).run())
                passed, feedback = (
                    task.verify(receipt.output)
                    if receipt.error is None
                    else (False, receipt.error)
                )
                row = {
                    "task_id": task.task_id,
                    "model": model,
                    "passed": passed,
                    "feedback": feedback,
                    "receipt": receipt.to_dict(),
                }
                report["rows"].append(row)
                output.write_text(json.dumps(report, indent=2))
                print(
                    json.dumps(
                        {
                            "task": task.task_id,
                            "model": model,
                            "passed": passed,
                            "tokens": receipt.usage.total_tokens,
                            "unknown": receipt.usage.unknown_calls,
                            "error": receipt.error,
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
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--size", type=int, default=14)
    args = parser.parse_args()
    asyncio.run(run(args.output, args.models, args.split, args.count, args.size))


if __name__ == "__main__":
    main()
