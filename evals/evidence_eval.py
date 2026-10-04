"""Evidence-grounded open-ended comparisons; disagreement is inconclusive.

Grounding guards validate quote/source identity only. The judge separately
checks inference validity, feasibility, the binding decision and measurable
trigger. Judge expense is measured separately from answer generation.
"""

from typing import Literal

from pydantic import BaseModel

from dialectica import workflow as wf


class EvidenceVerdict(BaseModel):
    winner: Literal["A", "B", "tie", "abstain"]
    reasoning: str


async def compare_answers(
    problem: str, candidate: str, baseline: str, judge_model: str
) -> dict:
    """Anonymous position-swapped comparison; abstention never becomes a tie."""

    async def script() -> dict:
        verdicts = []
        for index, (a, b) in enumerate(((candidate, baseline), (baseline, candidate))):
            verdict = await wf.agent(
                f"TASK AND EVIDENCE:\n{problem}\nANONYMOUS ANSWER A:\n{a}\n"
                f"ANONYMOUS ANSWER B:\n{b}\n"
                "Compare only their substantive merits. Check every factual number "
                "and inference against the supplied source cards; valid quotes do not "
                "prove inferences. Prefer feasible binding decisions with supported "
                "change triggers, explicit assumptions and a fair competing-option "
                "condition. Penalize fabricated facts, infeasible commitments and "
                "unsupported precision. Ignore prose style, model identity and length "
                "unless they affect usefulness. Return winner A, B, tie for comparable "
                "quality, or abstain if evidence is insufficient to compare, with reasoning.",
                schema=EvidenceVerdict,
                model=judge_model,
                label=f"evidence-judge-{index}",
                sees=[],
                max_attempts=1,
            )
            if not isinstance(verdict, EvidenceVerdict):
                raise TypeError("invalid evidence judge measurement")
            verdicts.append(verdict)
        first, second = verdicts
        if "abstain" in {first.winner, second.winner}:
            status, winner = "abstained", None
        else:
            left = {"A": "candidate", "B": "baseline", "tie": "tie"}[first.winner]
            right = {"A": "baseline", "B": "candidate", "tie": "tie"}[second.winner]
            status = "valid" if left == right else "position_disagreement"
            winner = left if status == "valid" else None
        return {
            "status": status,
            "winner": winner,
            "verdicts": [v.model_dump() for v in verdicts],
        }

    return await wf.workflow(script)
