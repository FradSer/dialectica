"""Blind A/B: Workflow engine vs single call, position-swapped judge.

Both arms use the SAME model. A separate judge model (or same, blind) compares
the two answers twice with positions swapped; disagreement = tie. The scorer
prints one number: net workflow wins (workflow_wins - single_wins) across N
problems. Reproduce the README's quality-ablation methodology on the Workflow
engine specifically.

Run: uv run python -m evals.workflow_ablation [--limit N --json out.json]
"""

import argparse
import asyncio
import json
import random

from dialectica import Workflow, agent, agent_runtime, parallel, phase, pipeline
from dialectica.agent_factory import create_agent
from dialectica.llm_config import get_model_config
from evals.baseline import BASELINE_INSTRUCTION
from evals.judge import BlindJudge, create_judge_agent
from evals.problems import DEFAULT_PROBLEMS

SINGLE = BASELINE_INSTRUCTION  # prompt-matched single call


async def single_arm(a, problem):
    return (await agent_runtime.run_agent(a, SINGLE.format(problem=problem))).strip()


async def workflow_arm(problem):
    async def script():
        phase("Gather")
        angles = ["broad", "critical", "practitioner", "stakeholder-opposition"]
        findings = await parallel(
            lambda: agent(
                f"Analyze this problem from a {x} angle. Be concrete and actionable:\n"
                f"- Name the single most important decision this angle forces.\n"
                f"- Give ONE concrete number, threshold, or magnitude that anchors it "
                f"(cost, headcount, time, rate — a real figure, not 'significant').\n"
                f"- State the ONE trade-off a naive answer would hand-wave.\n\n"
                f"PROBLEM:\n{problem}",
                label=f"g_{x}",
            )
            for x in angles
        )
        findings = [f for f in findings if f]
        phase("Critique")
        critiques = await pipeline(
            findings,
            lambda f, _, i: agent(
                f"Critique this analysis of the problem. Be the smartest skeptic in the room:\n"
                f"- Name the single most important concrete thing this analysis gets WRONG or LEAVES OUT.\n"
                f"- State the one question a decision-maker would ask that this analysis cannot answer.\n"
                f"- Give the specific correction the synthesis MUST make to not repeat this flaw.\n\n"
                f"PROBLEM:\n{problem}\n\nANALYSIS:\n{f}",
                label=f"c_{i}",
            ),
        )
        critiques = [c for c in critiques if c]
        phase("Synthesize")
        return await agent(
            f"You are the lead decision-maker. Write the final answer to:\n{problem}\n\n"
            f"You have angle analyses and their critiques. Your synthesis must be "
            f"BETTER than a single expert's first pass: concrete, specific, actionable, and "
            f"free of generic consultant prose.\n\n"
            f"Rules:\n"
            f"- Lead with the single sharpest recommendation and the precise trigger that "
            f"  decides it (a measurable condition, not 'when ready').\n"
            f"- Name the non-obvious failure mode a naive answer misses — the one the critiques "
            f"  flagged — and how this answer structurally avoids it.\n"
            f"- Carry forward the specific numbers, sequencing, and trade-offs from the analyses; "
            f"  do NOT abstract them into vagueness.\n"
            f"- Make a decisive recommendation, and state the condition under which the opposite "
            f"  choice would win.\n\n"
            f"ANALYSES:\n" + "\n\n".join(findings) + "\n\n"
            "CRITIQUES (address the weaknesses, do not repeat them):\n"
            + "\n\n".join(critiques),
            label="synth",
        )

    return await Workflow(script).run()


async def run(limit, judge_seed):
    problems = DEFAULT_PROBLEMS[:limit] if limit else DEFAULT_PROBLEMS
    solver = create_agent(
        role="Generator", role_name="Solver", model_config=get_model_config("GENERATOR")
    )
    judge = BlindJudge(create_judge_agent())
    random.seed(judge_seed)
    rows = []
    wf = sn = ti = 0
    for p in problems:
        w, s = await asyncio.gather(
            workflow_arm(p.statement), single_arm(solver, p.statement)
        )
        # BlindJudge.compare(problem, engine_answer, baseline_answer) internally
        # judges both orders (engine-first, baseline-first) and names the winner
        # "engine"/"baseline" by ARG POSITION. Pass engine first always; the
        # judge's internal position-swap handles position bias. Do NOT shuffle
        # arg order here — shuffling breaks the arg-position naming.
        res = await judge.compare(p.statement, w, s)
        winner = res.winner
        if winner == "engine":
            wf += 1
        elif winner == "baseline":
            sn += 1
        else:
            ti += 1
        rows.append({"id": p.id, "winner": winner})
        print(f"[{p.id}] winner={winner}", flush=True)
    return {"n": len(problems), "workflow": wf, "single": sn, "tie": ti, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge-seed", type=int, default=42)
    ap.add_argument("--json", type=str, default="")
    a = ap.parse_args()
    r = asyncio.run(run(a.limit, a.judge_seed))
    print(
        f"\n# workflow={r['workflow']} single={r['single']} tie={r['tie']} (n={r['n']})"
    )
    print(f"# NET workflow wins = {r['workflow'] - r['single']}")
    if a.json:
        json.dump(r, open(a.json, "w"), indent=2)


if __name__ == "__main__":
    main()
