"""Blind pairwise LLM judge with position-bias control.

The judge sees two anonymous answers (A and B) and picks a winner. Each pair
is judged twice with positions swapped; if the two verdicts disagree after
unswapping, the comparison is a tie — so a position-biased judge cannot
manufacture a winner. Configure the model with ``JUDGE_MODEL_CONFIG``.
"""

import logging

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field, ValidationError

from dialectica import agent_runtime
from dialectica.gan_evaluator import repair_json_escapes, strip_code_fence
from dialectica.llm_config import get_model_config

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an impartial judge comparing two candidate answers to a problem.

Your task:
- Judge only the answers' merits: correctness, completeness, specificity, actionability
- Ignore length, formatting and style unless they affect usefulness
- You do not know where either answer came from; treat them symmetrically
- Declare a tie only when the answers are genuinely comparable in quality"""

JUDGE_INSTRUCTION = """Compare the two candidate answers below.

**Problem:**
{problem}

**Answer A:**
{answer_a}

**Answer B:**
{answer_b}

Set winner to "A", "B", or "tie", and give a brief reasoning.
Return your verdict as a single JSON object."""


class JudgeVerdict(BaseModel):
    """The judge LLM's structured verdict for one A/B comparison.

    Used as an ADK ``output_schema``; kept Gemini-structured-output compatible
    (no ``extra='forbid'``, no enum/range constraints) — normalization happens
    in code instead.
    """

    winner: str = Field(default="tie", description='"A", "B", or "tie".')
    reasoning: str = Field(default="", description="Brief justification.")


class PairwiseResult(BaseModel):
    """Outcome of one engine-vs-baseline comparison (both judging orders)."""

    winner: str = Field(..., description='"engine", "baseline", or "tie".')
    verdicts: list[JudgeVerdict] = Field(
        default_factory=list, description="Raw verdicts, one per judging order."
    )


def create_judge_agent() -> LlmAgent:
    """Create the blind judge agent with structured verdict output."""
    return LlmAgent(
        name="Judge",
        instruction=JUDGE_SYSTEM_PROMPT,
        model=get_model_config("Judge"),
        output_schema=JudgeVerdict,
    )


def build_judge_instruction(problem: str, answer_a: str, answer_b: str) -> str:
    return JUDGE_INSTRUCTION.format(
        problem=problem, answer_a=answer_a, answer_b=answer_b
    )


def parse_judge_verdict(response: str) -> JudgeVerdict:
    """Parse the judge's JSON verdict; malformed output becomes a tie."""
    body = strip_code_fence(response)
    try:
        return JudgeVerdict.model_validate_json(body)
    except ValidationError:
        try:
            return JudgeVerdict.model_validate_json(repair_json_escapes(body))
        except ValidationError as e:
            logger.warning("Judge returned unparseable verdict: %s", e)
            return JudgeVerdict(winner="tie", reasoning="Unparseable judge output.")


def _position_of(verdict: JudgeVerdict) -> str:
    """Normalize the verdict's winner to "A", "B" or "tie"."""
    winner = verdict.winner.strip().upper()
    return winner if winner in {"A", "B"} else "tie"


class BlindJudge:
    """Compares an engine answer and a baseline answer without attribution."""

    def __init__(self, agent: LlmAgent):
        self.agent = agent

    async def compare(
        self, problem: str, engine_answer: str, baseline_answer: str
    ) -> PairwiseResult:
        """Judge both orders and return the unswapped, bias-controlled winner."""
        first = await self._judge_once(problem, engine_answer, baseline_answer)
        second = await self._judge_once(problem, baseline_answer, engine_answer)

        label_first = {"A": "engine", "B": "baseline"}.get(_position_of(first), "tie")
        label_second = {"A": "baseline", "B": "engine"}.get(_position_of(second), "tie")
        winner = label_first if label_first == label_second else "tie"
        return PairwiseResult(winner=winner, verdicts=[first, second])

    async def _judge_once(
        self, problem: str, answer_a: str, answer_b: str
    ) -> JudgeVerdict:
        instruction = build_judge_instruction(problem, answer_a, answer_b)
        return parse_judge_verdict(
            await agent_runtime.run_agent(self.agent, instruction)
        )
