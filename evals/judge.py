"""Blind pairwise LLM judge with position-bias control.

The judge sees two anonymous answers (A and B) and picks a winner. Each pair
is judged twice with positions swapped; if the two verdicts disagree after
unswapping, the comparison is a tie — so a position-biased judge cannot
manufacture a winner. Configure the model with ``JUDGE_MODEL_CONFIG``.
"""

import json
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
    """The judge LLM's verdict for one A/B comparison (prompt-driven JSON)."""

    winner: str = Field(default="tie", description='"A", "B", or "tie".')
    reasoning: str = Field(default="", description="Brief justification.")
    parse_failed: bool = Field(
        default=False,
        description="True if the verdict was empty/unparseable (re-ask, do not tie).",
    )


class PairwiseResult(BaseModel):
    """Outcome of one engine-vs-baseline comparison (both judging orders)."""

    winner: str = Field(..., description='"engine", "baseline", or "tie".')
    verdicts: list[JudgeVerdict] = Field(
        default_factory=list, description="Raw verdicts, one per judging order."
    )


def create_judge_agent() -> LlmAgent:
    """Create the blind judge agent (prompt-driven JSON, no enforced schema).

    Enforced JSON mode makes some proxy backends (e.g. the qwen proxy) return
    empty/truncated output, which a defaulted schema reads as a silent tie and
    biases every comparison toward ties. ``parse_judge_verdict`` parses the
    prompt-driven JSON and flags empties so the caller re-asks instead.
    """
    return LlmAgent(
        name="Judge",
        instruction=JUDGE_SYSTEM_PROMPT,
        model=get_model_config("Judge"),
    )


def build_judge_instruction(problem: str, answer_a: str, answer_b: str) -> str:
    return JUDGE_INSTRUCTION.format(
        problem=problem, answer_a=answer_a, answer_b=answer_b
    )


def parse_judge_verdict(response: str) -> JudgeVerdict:
    """Parse the judge's JSON verdict.

    An empty body, non-JSON, or JSON with no real ``winner`` is a *failed*
    measurement (``parse_failed=True``), NOT a tie — silently coding empties as
    ties biases every comparison toward ties. The caller re-asks on failure.
    """
    body = strip_code_fence(response or "").strip()
    if not body:
        return JudgeVerdict(reasoning="Empty judge output.", parse_failed=True)
    for candidate in (body, repair_json_escapes(body)):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and str(data.get("winner", "")).strip():
            try:
                return JudgeVerdict.model_validate(data)
            except ValidationError:
                continue
    logger.warning("Judge returned empty/unparseable verdict: %r", body[:120])
    return JudgeVerdict(reasoning="Unparseable judge output.", parse_failed=True)


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
        self, problem: str, answer_a: str, answer_b: str, max_attempts: int = 3
    ) -> JudgeVerdict:
        """Judge one order, re-asking on an empty/unparseable verdict.

        Mirrors ``gan_evaluator.score_thought``: some proxies transiently return
        empty output, and a swallowed empty would silently become a tie.
        """
        instruction = build_judge_instruction(problem, answer_a, answer_b)
        verdict = parse_judge_verdict(
            await agent_runtime.run_agent(self.agent, instruction)
        )
        for attempt in range(2, max_attempts + 1):
            if not verdict.parse_failed:
                return verdict
            logger.warning(
                "Empty/unparseable judge verdict, re-asking (attempt %d/%d)",
                attempt,
                max_attempts,
            )
            verdict = parse_judge_verdict(
                await agent_runtime.run_agent(self.agent, instruction)
            )
        return verdict
