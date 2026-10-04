"""Research implementation of CLR's inference mechanism, not benchmark replication.

Source: https://arxiv.org/html/2608.11994v1, equations 2/3. Each candidate
contains five decision-critical claims. Independent assessment sees the task
and claims, never the full trace or a separate answer. Reliability is surviving
fraction ** claim count; equivalent answers sum support. This heuristic is not
a correctness probability. No hidden verifier is used to select the answer.
Model, tasks and structured decoding differ from the paper's experiments.
"""

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, StrictBool

from dialectica import workflow as wf


class ClaimCandidate(BaseModel):
    answer: str = Field(min_length=1)
    claims: list[str] = Field(min_length=5, max_length=5)


class ClaimVerdicts(BaseModel):
    survived: list[StrictBool] = Field(min_length=5, max_length=5)


def select_candidate(
    candidates: list[ClaimCandidate],
    verdicts: list[ClaimVerdicts],
    answer_key: Callable[[str], Hashable] = str,
) -> str:
    """Weighted consensus; a prediction parser signals omissions via ValueError.

    Tied groups select the earliest parsed representative. The default string
    key accepts all nonempty text; structured tasks must supply their parser.
    """
    if not candidates or len(candidates) != len(verdicts):
        raise ValueError("candidate and verdict lists must be nonempty and aligned")
    support: dict[Hashable, float] = {}
    representatives: dict[Hashable, str] = {}
    for candidate, verdict in zip(candidates, verdicts, strict=True):
        try:
            key = answer_key(candidate.answer)
        except ValueError:
            continue
        representatives.setdefault(key, candidate.answer)
        fraction = sum(verdict.survived) / len(verdict.survived)
        support[key] = support.get(key, 0) + fraction ** len(verdict.survived)
    if not support:
        raise ValueError("no parsed candidate predictions")
    return representatives[max(support, key=support.__getitem__)]


@dataclass
class ClaimFalsificationEngine:
    problem: str
    model: str | None = None
    verifier_model: str | None = None
    samples: int = 2
    answer_key: Callable[[str], Hashable] = str

    async def run(self) -> dict[str, Any]:
        async def script() -> dict[str, Any]:
            candidates = []
            for index in range(self.samples):
                candidate = await wf.agent(
                    f"{self.problem}\nSolve carefully. Put the final task answer in answer. "
                    "Include exactly five concise decision-critical claims whose failure "
                    "would undermine the answer; omit routine summaries and answer restatements.",
                    schema=ClaimCandidate,
                    model=self.model,
                    label=f"claim-candidate-{index}",
                    sees=[],
                    max_attempts=1,
                )
                if not isinstance(candidate, ClaimCandidate):
                    raise TypeError("invalid claim candidate measurement")
                candidates.append(candidate)
            verdicts = []
            for index, candidate in enumerate(candidates):
                verdict = await wf.agent(
                    f"PROBLEM:\n{self.problem}\nCLAIMS:\n"
                    + "\n".join(
                        f"{i}: {claim}" for i, claim in enumerate(candidate.claims)
                    )
                    + "\nSearch each claim for a decisive contradiction, counterexample, "
                    "missing condition or unsupported inference, including conflicts between "
                    "claims. survived is five booleans in claim order: false if refuted, "
                    "true otherwise. Not refuted does not mean proved. Do not solve anew.",
                    schema=ClaimVerdicts,
                    model=self.verifier_model or self.model,
                    label=f"claim-assessment-{index}",
                    sees=[],
                    max_attempts=1,
                )
                if not isinstance(verdict, ClaimVerdicts):
                    raise TypeError("invalid claim assessment measurement")
                verdicts.append(verdict)
            return {
                "final_answer": select_candidate(candidates, verdicts, self.answer_key),
                "candidates": [c.model_dump() for c in candidates],
                "verdicts": [v.model_dump() for v in verdicts],
            }

        return await wf.workflow(script)


def create_claim_falsification_engine(
    problem: str,
    *,
    model: str | None = None,
    verifier_model: str | None = None,
    samples: int = 2,
    answer_key: Callable[[str], Hashable] = str,
) -> ClaimFalsificationEngine:
    if samples < 1:
        raise ValueError("samples must be positive")
    return ClaimFalsificationEngine(problem, model, verifier_model, samples, answer_key)
