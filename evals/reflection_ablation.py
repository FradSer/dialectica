"""Three-arm ablation: heterogeneous reflection vs homogeneous vs single call.

Open-ended meta problems (no ground truth). Tests whether assigning different
models to parallel gather angles improves answer quality over (b) the same
multi-stage pipeline on one model and (c) a prompt-matched single call.

Three arms, judged blind with position-swap (disagreement = tie):
  (a) hetero reflection — create_reflection_engine with default 2-model roster,
      angles round-robin across models.
  (b) homo reflection   — same pipeline, every stage on roster[0].
  (c) single call       — BASELINE_INSTRUCTION via agent_runtime.run_agent.

Primary: (a) net-wins vs (c). Secondary: (a) net-wins vs (b) isolates heterogeneity
from pipeline shape.

NOT run in CI. Needs a live multi-provider roster (cliproxy/openai: here).
Run: uv run python -m evals.reflection_ablation [--limit N --json out.json]
"""

import argparse
import asyncio
import json
import os
import random

from dialectica import agent_runtime
from dialectica.agent_factory import create_agent
from dialectica.llm_config import get_model_config
from evals.baseline import BASELINE_INSTRUCTION
from evals.harness import count_agent_calls
from evals.judge import BlindJudge, create_judge_agent
from evals.meta_problems import META_PROBLEMS
from evals.problems import DEFAULT_PROBLEMS
from examples.patterns.reflection_pattern import (
    DEFAULT_ANGLES,
    DEFAULT_ROSTER,
    create_reflection_engine,
)

SINGLE = BASELINE_INSTRUCTION


async def hetero_arm(problem: str, roster: list[str]) -> str:
    engine = create_reflection_engine(problem, roster=roster)
    result = await engine.run()
    return result["final_answer"].strip()


async def homo_arm(problem: str, model: str) -> str:
    engine = create_reflection_engine(
        problem,
        angle_models={a: model for a in DEFAULT_ANGLES},
        frame_model=model,
        critique_model=model,
        synthesize_model=model,
    )
    result = await engine.run()
    return result["final_answer"].strip()


async def single_arm(problem: str, solver) -> str:
    return (
        await agent_runtime.run_agent(solver, SINGLE.format(problem=problem))
    ).strip()


def _problem_pool(limit: int | None) -> list:
    pool = (
        META_PROBLEMS
        if os.environ.get("WORKFLOW_PROBLEM_SET", "meta") != "default"
        else DEFAULT_PROBLEMS
    )
    return pool[:limit] if limit else pool


async def run(limit: int | None, roster: list[str], judge_seed: int) -> dict:
    problems = _problem_pool(limit)
    homo_model = roster[0]
    solver = create_agent(
        role="Generator", role_name="Solver", model_config=get_model_config("GENERATOR")
    )
    judge = BlindJudge(create_judge_agent())
    random.seed(judge_seed)

    rows = []
    hetero_vs_single_w = hetero_vs_single_l = hetero_vs_single_t = 0
    hetero_vs_homo_w = hetero_vs_homo_l = hetero_vs_homo_t = 0
    call_counts: list[int] = []

    for p in problems:
        with count_agent_calls() as counter:
            hetero, homo, single = await asyncio.gather(
                hetero_arm(p.statement, roster),
                homo_arm(p.statement, homo_model),
                single_arm(p.statement, solver),
            )
        call_counts.append(counter.count)

        vs_single = await judge.compare(p.statement, hetero, single)
        vs_homo = await judge.compare(p.statement, hetero, homo)

        if vs_single.winner == "engine":
            hetero_vs_single_w += 1
        elif vs_single.winner == "baseline":
            hetero_vs_single_l += 1
        else:
            hetero_vs_single_t += 1

        if vs_homo.winner == "engine":
            hetero_vs_homo_w += 1
        elif vs_homo.winner == "baseline":
            hetero_vs_homo_l += 1
        else:
            hetero_vs_homo_t += 1

        rows.append(
            {
                "id": p.id,
                "hetero_vs_single": vs_single.winner,
                "hetero_vs_homo": vs_homo.winner,
                "calls": counter.count,
            }
        )
        print(
            f"[{p.id}] hetero_vs_single={vs_single.winner} "
            f"hetero_vs_homo={vs_homo.winner} calls={counter.count}",
            flush=True,
        )

    return {
        "n": len(problems),
        "roster": roster,
        "homo_model": homo_model,
        "hetero_vs_single": {
            "hetero_wins": hetero_vs_single_w,
            "single_wins": hetero_vs_single_l,
            "ties": hetero_vs_single_t,
        },
        "hetero_vs_homo": {
            "hetero_wins": hetero_vs_homo_w,
            "homo_wins": hetero_vs_homo_l,
            "ties": hetero_vs_homo_t,
        },
        "avg_calls_per_problem": sum(call_counts) / len(call_counts)
        if call_counts
        else 0,
        "rows": rows,
    }


def render(report: dict) -> str:
    n = report["n"]
    vs_s = report["hetero_vs_single"]
    vs_h = report["hetero_vs_homo"]
    hw, sw, st = vs_s["hetero_wins"], vs_s["single_wins"], vs_s["ties"]
    hh, hm, ht = vs_h["hetero_wins"], vs_h["homo_wins"], vs_h["ties"]
    net_vs_single = hw - sw
    net_vs_homo = hh - hm
    return f"""# Reflection ablation — {n} problems
Roster (hetero): {report["roster"]}
Homo arm model: {report["homo_model"]}
Avg LLM calls/problem (all three arms): {report["avg_calls_per_problem"]:.1f}

## (a) hetero vs (c) single — blind position-swap judge
| hetero wins | single wins | ties |
|---|---|---|
| {hw} | {sw} | {st} |
NET hetero wins vs single = **{net_vs_single}**

## (a) hetero vs (b) homo — isolates model heterogeneity
| hetero wins | homo wins | ties |
|---|---|---|
| {hh} | {hm} | {ht} |
NET hetero wins vs homo = **{net_vs_homo}**
"""


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Heterogeneous reflection vs homo vs single on meta problems."
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge-seed", type=int, default=42)
    ap.add_argument(
        "--roster",
        type=str,
        default=None,
        help="comma-separated provider:model configs for hetero arm",
    )
    ap.add_argument("--json", type=str, default="")
    args = ap.parse_args()
    roster = args.roster.split(",") if args.roster else DEFAULT_ROSTER
    limit = args.limit or None
    report = asyncio.run(run(limit, roster, args.judge_seed))
    print(render(report))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
