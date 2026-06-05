"""Adversarial evaluators implementing the ``Evaluator`` protocol.

``AdversarialEvaluator`` runs the full GAN loop (discriminator critique ->
generator refinement -> re-score). ``SinglePassEvaluator`` does one scoring
call with no refinement — a cheaper drop-in for the same interface.
"""

import logging
from typing import Any

from google.adk.agents import LlmAgent
from pydantic import ValidationError

from . import agent_runtime
from .models import DiscriminatorVerdict, EvaluationResult

logger = logging.getLogger(__name__)


def _format_context(context: dict[str, Any]) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in context.items() if v)


def build_discriminator_instruction(thought: str, context: dict[str, Any]) -> str:
    return f"""Evaluate the following thought critically:

**Thought:**
{thought}

**Context:**
{_format_context(context)}

**Evaluation Criteria:**
1. **Soundness**: Is the thought logically sound and feasible?
2. **Completeness**: Does it address the problem adequately?
3. **Innovation**: Does it offer novel or valuable insights?
4. **Practicality**: Can it be implemented effectively?

Score the thought from 0 to 10, list specific flaws and actionable suggestions,
give a brief reasoning, and set should_terminate to true only if the path is
fundamentally flawed. Be rigorous but constructive.
"""


def parse_verdict(response: str) -> EvaluationResult:
    """Parse the Discriminator's structured JSON verdict into an EvaluationResult.

    The Discriminator uses ``output_schema=DiscriminatorVerdict``, so the
    response is JSON. If the model still returns malformed output, the thought
    is scored 0.0 so the search prunes it rather than crashing the run.
    """
    try:
        verdict = DiscriminatorVerdict.model_validate_json(response)
        return EvaluationResult.from_verdict(verdict)
    except ValidationError as e:
        logger.warning("Discriminator returned unparseable verdict: %s", e)
        return EvaluationResult(score=0.0, reasoning="Unparseable discriminator output.")


async def score_thought(
    discriminator: LlmAgent, thought: str, context: dict[str, Any]
) -> EvaluationResult:
    """Run one discriminator scoring pass on ``thought``."""
    instruction = build_discriminator_instruction(thought, context)
    return parse_verdict(await agent_runtime.run_agent(discriminator, instruction))


def _round_record(round_num: int, thought: str, result: EvaluationResult) -> dict[str, Any]:
    return {
        "round": round_num,
        "thought": thought,
        "score": result.score,
        "flaws": result.flaws,
        "suggestions": result.suggestions,
        "reasoning": result.reasoning,
    }


class SinglePassEvaluator:
    """Score a thought once, with no refinement loop (cheap Evaluator)."""

    def __init__(self, discriminator: LlmAgent):
        self.discriminator = discriminator

    async def evaluate(self, thought_content: str, context: dict[str, Any]) -> EvaluationResult:
        result = await score_thought(self.discriminator, thought_content, context)
        result.adversarial_rounds = 1
        result.history = [_round_record(1, thought_content, result)]
        result.refined_thought = thought_content
        return result


class AdversarialEvaluator:
    """GAN-style evaluator: critique -> refine -> re-score until good enough.

    The Generator proposes refinements while the Discriminator critiques. The
    loop stops when the score clears ``score_threshold``, the Discriminator
    recommends termination, or ``max_rounds`` is exhausted.
    """

    def __init__(
        self,
        generator: LlmAgent,
        discriminator: LlmAgent,
        max_rounds: int = 3,
        score_threshold: float = 7.0,
    ):
        self.generator = generator
        self.discriminator = discriminator
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold

    async def evaluate(
        self,
        thought_content: str,
        context: dict[str, Any],
    ) -> EvaluationResult:
        """Run the adversarial refinement loop and return the final result.

        ``EvaluationResult.refined_thought`` carries the (possibly improved)
        text the returned score applies to.
        """
        current_thought = thought_content
        history: list[dict[str, Any]] = []
        best: EvaluationResult | None = None
        best_thought = thought_content

        logger.info(f"Starting GAN evaluation (max {self.max_rounds} rounds)")

        for round_num in range(1, self.max_rounds + 1):
            logger.info(f"GAN round {round_num}/{self.max_rounds}")

            eval_result = await score_thought(self.discriminator, current_thought, context)
            history.append(_round_record(round_num, current_thought, eval_result))

            logger.info(
                f"Round {round_num}: score={eval_result.score:.1f}, "
                f"flaws={len(eval_result.flaws)}, suggestions={len(eval_result.suggestions)}"
            )

            # Refinement is not monotonic: keep the best-scoring round, not the last.
            if best is None or eval_result.score > best.score:
                best, best_thought = eval_result, current_thought

            if eval_result.should_terminate:
                logger.info("Discriminator recommends termination")
                break

            if eval_result.score >= self.score_threshold:
                logger.info(f"Quality threshold reached: {eval_result.score:.1f} >= {self.score_threshold}")
                break

            # Refine for the next round, based on the latest critique.
            if round_num < self.max_rounds:
                current_thought = await self._refine(current_thought, eval_result, context)
                logger.info("Generator refined thought based on feedback")
        else:
            logger.info(f"Max rounds ({self.max_rounds}) reached")

        best.adversarial_rounds = len(history)
        best.history = history
        best.refined_thought = best_thought
        return best

    async def _refine(
        self,
        thought: str,
        eval_result: EvaluationResult,
        context: dict[str, Any],
    ) -> str:
        """Ask the generator to improve ``thought`` given the discriminator feedback."""
        flaws_str = "\n".join(f"- {f}" for f in eval_result.flaws)
        suggestions_str = "\n".join(f"- {s}" for s in eval_result.suggestions)

        instruction = f"""Refine the following thought based on critical feedback:

**Original Thought:**
{thought}

**Context:**
{_format_context(context)}

**Identified Flaws:**
{flaws_str}

**Suggestions for Improvement:**
{suggestions_str}

**Discriminator's Reasoning:**
{eval_result.reasoning}

**Your Task:**
Address the identified flaws and incorporate the suggestions to create an improved version of the thought. Maintain the core intent while strengthening weak points.

**Output Format:**
Provide the refined thought directly, without introductory text or commentary.
"""
        response = await agent_runtime.run_agent(self.generator, instruction)
        return response.strip()
