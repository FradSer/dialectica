"""Expanded multi-model quality workflow ablation — modes vs single call.

Tests whether scheduling heterogeneous models across workflow stages — via
reflection, adversarial rival, or one-round dialectic — beats a prompt-matched
single call on an expanded problem pool (meta + default = 10 problems).

Five arms per problem (blind position-swap judge, disagreement = tie):
  (a) single call            — BASELINE_INSTRUCTION
  (b) homo reflection        — reflection_pattern, one model
  (c) hetero reflection      — quality_workflow mode=reflection
  (d) hetero adversarial     — quality_workflow mode=adversarial
  (e) hetero dialectic       — quality_workflow mode=dialectic

Primary comparisons vs (a): net wins per arm. Secondary: (d)/(e) vs (c) to see
if extra adversarial/dialectic stages add lift beyond hetero reflection alone.

NOT run in CI. Needs cliproxy (`OPENAI_API_BASE`/`OPENAI_API_KEY`).
Run: uv run python -m evals.quality_workflow_ablation [--limit N --json out.json]
"""

import argparse
import asyncio
import json
import os

from dialectica import agent_runtime
from dialectica.agent_factory import create_agent
from dialectica.llm_config import get_model_config
from evals.baseline import BASELINE_INSTRUCTION
from evals.harness import count_agent_calls
from evals.judge import BlindJudge, create_judge_agent
from evals.meta_problems import META_PROBLEMS
from evals.problems import DEFAULT_PROBLEMS
from examples.patterns.quality_workflow_pattern import (
    DEFAULT_ROSTER,
    QualityMode,
    create_quality_workflow_engine,
)
from examples.patterns.reflection_pattern import (
    DEFAULT_ANGLES,
    create_reflection_engine,
)

SINGLE = BASELINE_INSTRUCTION

ALL_PROBLEMS = META_PROBLEMS + DEFAULT_PROBLEMS

ARM_LABELS = {
    "homo_reflection": "homo reflection",
    "hetero_reflection": "hetero reflection",
    "hetero_adversarial": "hetero adversarial",
    "hetero_dialectic": "hetero dialectic",
}


async def single_arm(problem: str, solver) -> str:
    return (
        await agent_runtime.run_agent(solver, SINGLE.format(problem=problem))
    ).strip()


async def homo_arm(problem: str, model: str) -> str:
    engine = create_reflection_engine(
        problem,
        angle_models={a: model for a in DEFAULT_ANGLES},
        frame_model=model,
        critique_model=model,
        synthesize_model=model,
    )
    return (await engine.run())["final_answer"].strip()


async def mode_arm(problem: str, mode: QualityMode, roster: list[str]) -> str:
    engine = create_quality_workflow_engine(problem, mode, roster=roster)
    return (await engine.run())["final_answer"].strip()


def _problem_pool(limit: int | None) -> list:
    return ALL_PROBLEMS[:limit] if limit else ALL_PROBLEMS


async def run(limit: int | None, roster: list[str], judge_seed: int) -> dict:
    problems = _problem_pool(limit)
    homo_model = roster[0]
    solver = create_agent(
        role="Generator", role_name="Solver", model_config=get_model_config("GENERATOR")
    )
    judge = BlindJudge(create_judge_agent())

    arms = [
        "homo_reflection",
        "hetero_reflection",
        "hetero_adversarial",
        "hetero_dialectic",
    ]
    totals = {arm: {"wins": 0, "losses": 0, "ties": 0} for arm in arms}
    vs_reflection = {
        "hetero_adversarial": {"wins": 0, "losses": 0, "ties": 0},
        "hetero_dialectic": {"wins": 0, "losses": 0, "ties": 0},
    }
    rows: list[dict] = []

    for p in problems:
        with count_agent_calls() as counter:
            single, homo, hetero_refl, hetero_adv, hetero_dial = await asyncio.gather(
                single_arm(p.statement, solver),
                homo_arm(p.statement, homo_model),
                mode_arm(p.statement, "reflection", roster),
                mode_arm(p.statement, "adversarial", roster),
                mode_arm(p.statement, "dialectic", roster),
            )

        answers = {
            "homo_reflection": homo,
            "hetero_reflection": hetero_refl,
            "hetero_adversarial": hetero_adv,
            "hetero_dialectic": hetero_dial,
        }

        row: dict = {"id": p.id, "calls": counter.count}
        for arm in arms:
            res = await judge.compare(p.statement, answers[arm], single)
            row[f"{arm}_vs_single"] = res.winner
            if res.winner == "engine":
                totals[arm]["wins"] += 1
            elif res.winner == "baseline":
                totals[arm]["losses"] += 1
            else:
                totals[arm]["ties"] += 1

        for extra in ("hetero_adversarial", "hetero_dialectic"):
            res = await judge.compare(
                p.statement, answers[extra], answers["hetero_reflection"]
            )
            row[f"{extra}_vs_reflection"] = res.winner
            if res.winner == "engine":
                vs_reflection[extra]["wins"] += 1
            elif res.winner == "baseline":
                vs_reflection[extra]["losses"] += 1
            else:
                vs_reflection[extra]["ties"] += 1

        rows.append(row)
        print(
            f"[{p.id}] "
            + " ".join(f"{a}={row[f'{a}_vs_single']}" for a in arms)
            + f" calls={counter.count}",
            flush=True,
        )

    return {
        "n": len(problems),
        "roster": roster,
        "homo_model": homo_model,
        "pool": "meta+default",
        "vs_single": totals,
        "vs_reflection": vs_reflection,
        "rows": rows,
    }


def _net(t: dict) -> int:
    return t["wins"] - t["losses"]


def render(report: dict) -> str:
    n = report["n"]
    lines = [
        f"# Quality workflow ablation — {n} problems ({report['pool']})",
        f"Roster: {report['roster']}",
        f"Homo model: {report['homo_model']}",
        "",
        "## vs single call (blind position-swap)",
        "| arm | wins | losses | ties | NET |",
        "|---|---|---|---|---|",
    ]
    for arm, label in ARM_LABELS.items():
        t = report["vs_single"][arm]
        lines.append(
            f"| {label} | {t['wins']} | {t['losses']} | {t['ties']} | {_net(t)} |"
        )
    lines.extend(
        [
            "",
            "## vs hetero reflection (does extra stage help?)",
            "| arm | wins | losses | ties | NET |",
            "|---|---|---|---|---|",
        ]
    )
    for arm in ("hetero_adversarial", "hetero_dialectic"):
        t = report["vs_reflection"][arm]
        lines.append(
            f"| {ARM_LABELS[arm]} | {t['wins']} | {t['losses']} | {t['ties']} | {_net(t)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Multi-model quality workflow modes vs single on expanded pool."
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge-seed", type=int, default=42)
    ap.add_argument("--roster", type=str, default=None)
    ap.add_argument("--json", type=str, default="")
    args = ap.parse_args()
    roster = args.roster.split(",") if args.roster else DEFAULT_ROSTER
    limit = args.limit or None
    report = asyncio.run(run(limit, roster, args.judge_seed))
    print(render(report))
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
