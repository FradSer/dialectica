"""Honesty-gate for the ensemble on OPEN-ENDED tasks (LLM-as-judge robustness).

The code-verifier ablation (ensemble_ablation.py) measures pass-rate on
verifiable code; on novel code both models saturate, so H1 is unfalsifiable
there. This companion tests the *robustness* dimension the user actually cares
about: on open-ended meta problems (no ground truth), does a heterogeneous
ensemble guided by an LLM scorer produce an answer a blind judge rates as
stronger than a prompt-matched single call?

Three arms, all LLM-call-counted through the single seam, judged blind with
position-swap (disagreement = tie, the repo's standard):
  (a) ensemble + LLM scorer   — create_ensemble_engine, scorer = a judge-model
                                 rating answer quality 0..1.
  (b) single call (matched prompt) — the BASELINE_INSTRUCTION single pass.
  (c) ensemble blind-pick     — same roster, scorer replaced by a constant
                                 (signal-free); isolates signal vs heterogeneity.

KEEP only if (a) net-wins > (b) AND (a) net-wins > (c) on the blind judge.

NOT run in CI. Needs a live multi-provider roster (cliproxy/openai: here).
Run: uv run python -m evals.ensemble_meta_ablation [--limit N --budget N --json out]
"""

import argparse
import asyncio
import json
import random

from dialectica import (
    agent_runtime,
    create_ensemble_engine,
)
from dialectica.agent_factory import create_agent
from dialectica.llm_config import get_model_config
from evals.baseline import BASELINE_INSTRUCTION
from evals.judge import BlindJudge, create_judge_agent
from evals.meta_problems import META_PROBLEMS

SINGLE = BASELINE_INSTRUCTION  # prompt-matched single call

DEFAULT_ROSTER: list[str] = ["openai:qwen3.6-flash", "openai:glm-5.2"]
# The scorer is a separate LLM (a judge-style quality rating 0..1). Use a
# different model than the solvers when possible to avoid self-praise bias.
DEFAULT_SCORER_MODEL = "openai:qwen3.6-max-preview"

SCORER_SYSTEM = """You rate answer quality on a 0..1 scale (1.0 = excellent, 0.0 = poor).
Consider: concrete grounding (real numbers/thresholds, not vagueness), decisiveness
(one binding recommendation, not option-listing), handling of the core tension,
and non-obvious failure modes. Return JSON: {"score": <float>, "reason": "<short>"}.
Be strict; a generic consultant-style answer scores <= 0.4."""


def _make_llm_scorer(scorer_model: str):
    """Build an injected scorer that rates an answer 0..1 via an LLM call.

    The scorer runs through the same single seam (run_agent) so its calls are
    counted in the arm's budget — i.e. the ensemble pays for its own signal.
    """
    from dialectica.llm_config import _parse_model_config

    scorer_agent = create_agent(
        role="Generator",
        role_name="Scorer",
        model_config=_parse_model_config(scorer_model),
        additional_context=SCORER_SYSTEM,
    )

    async def score(answer: str) -> float:
        from dialectica.gan_evaluator import repair_json_escapes, strip_code_fence

        prompt = (
            f"{SCORER_SYSTEM}\n\nRate this answer (JSON only):\n\n{answer[:1500]}"
        )
        raw = (await agent_runtime.run_agent(scorer_agent, prompt)).strip()
        body = strip_code_fence(raw).strip()
        try:
            data = json.loads(body if body else repair_json_escapes(raw))
            return max(0.0, min(1.0, float(data.get("score", 0.0))))
        except (ValueError, TypeError):
            return 0.0

    return score


async def ensemble_arm(problem: str, roster: list[str], budget: int, scorer):
    e = create_ensemble_engine(
        problem,
        scorer=scorer,
        models=roster,
        max_calls=budget,
    )
    r = await e.run()
    return r["final_answer"].strip()


async def blind_ensemble_arm(problem: str, roster: list[str], budget: int):
    e = create_ensemble_engine(
        problem,
        scorer=lambda _a: 0.5,  # signal-free
        models=roster,
        max_calls=budget,
    )
    r = await e.run()
    return r["final_answer"].strip()


async def single_arm(problem: str, solver):
    return (await agent_runtime.run_agent(solver, SINGLE.format(problem=problem))).strip()


async def run(limit, budget, roster, scorer_model, judge_seed):
    problems = META_PROBLEMS[:limit] if limit else META_PROBLEMS
    solver = create_agent(
        role="Generator", role_name="Solver", model_config=get_model_config("GENERATOR")
    )
    judge = BlindJudge(create_judge_agent())
    scorer = _make_llm_scorer(scorer_model)
    random.seed(judge_seed)

    rows = []
    a_wins = b_wins = c_wins = 0  # net wins vs single
    a_ties = c_ties = 0
    for p in problems:
        a, c, s = await asyncio.gather(
            ensemble_arm(p.statement, roster, budget, scorer),
            blind_ensemble_arm(p.statement, roster, budget),
            single_arm(p.statement, solver),
        )
        # arm (b) IS the single call (s) — matched-prompt baseline.
        res_a = await judge.compare(p.statement, a, s)  # ensemble vs single
        res_c = await judge.compare(p.statement, c, s)  # blind vs single
        wina = res_a.winner
        winc = res_c.winner
        if wina == "engine":
            a_wins += 1
        elif wina == "baseline":
            b_wins += 1
        else:
            a_ties += 1
        if winc == "engine":
            c_wins += 1
        elif winc == "baseline":
            b_wins += 1  # blind loses to single counts as single beating blind
        else:
            c_ties += 1
        rows.append(
            {
                "id": p.id,
                "ensemble_vs_single": wina,
                "blind_vs_single": winc,
            }
        )
        print(f"[{p.id}] ens_vs_single={wina} blind_vs_single={winc}", flush=True)

    return {
        "n": len(problems),
        "budget": budget,
        "roster": roster,
        "ensemble_beats_single": a_wins,
        "single_beats_ensemble": b_wins,
        "ensemble_ties": a_ties,
        "blind_beats_single": c_wins,
        "blind_ties": c_ties,
        "rows": rows,
    }


def render(md: dict) -> str:
    n = md["n"]
    a = md["ensemble_beats_single"]
    bl = md["single_beats_ensemble"]
    c = md["blind_beats_single"]
    ct = md["blind_ties"]
    at = md["ensemble_ties"]
    verdict_a = "WIN" if a > bl else ("TIE" if a == bl else "LOSE")
    verdict_c = "signal-attributable" if a > c else "not-attributable"
    keep = a > bl and a > c
    return f"""# Ensemble meta ablation (LLM-judge robustness) — {n} problems, budget N={md['budget']}
Roster: {md['roster']}
## Blind position-swap judge: net wins vs single call
| arm | beats single | loses to single | ties |
|---|---|---|---|
| (a) ensemble + LLM scorer | {a} | {bl} | {at} |
| (c) ensemble blind-pick  | {c} | {bl} | {ct} |
(a) vs single: **{verdict_a}** (ensemble {a}-{bl}-{at})
Signal-attribution: (a) beats-single {a} vs (c) beats-single {c} -> **{verdict_c}**
**{'KEEP' if keep else 'CUT'}** — {'ensemble+signal beats both single and blind' if keep else 'ensemble does not beat both single and blind; the robustness gain is not attributable to signal+heterogeneity'}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Ensemble vs single on meta problems, LLM judge.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--budget", type=int, default=6, help="max_calls for ensemble arms")
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--roster", type=str, default=None, help="comma-separated provider:model")
    ap.add_argument("--scorer-model", type=str, default=DEFAULT_SCORER_MODEL)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    roster = args.roster.split(",") if args.roster else DEFAULT_ROSTER
    md = asyncio.run(
        run(args.limit, args.budget, roster, args.scorer_model, args.seed)
    )
    print(render(md))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(md, f, indent=2)


if __name__ == "__main__":
    main()
