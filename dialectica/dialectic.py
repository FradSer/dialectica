"""The dialectical kernel — Dialectica's soul.

Not breadth-first Tree-of-Thoughts (generate many candidates, score, keep the
best). The evals showed that scaffold buys nothing over a single strong call
at matched cost, and a fan-out/judge-panel workflow already does
"many candidates, then vote".

The soul is the dialectic the name promises — **thesis → antithesis →
synthesis** — run intelligently:

1. Understand first. Name the problem's core tension (its inner
   contradiction) before opposing anything. If the problem has no genuine
   tension (a factual/determinate task), skip the dialectic entirely — the
   engine knows when NOT to dialecticize.
2. Oppose with a rival, not a critique. The antithesis is a COMPLETE
   alternative solution committed to the opposite side of the core tension —
   not a list of the thesis's flaws (that is GAN-style refine, which the data
   showed adds nothing).
3. Synthesize beyond both. Integrate the conflicting truths into a higher
   solution neither side held.
4. Spiral. The synthesis becomes the next thesis and faces opposition along
   axes not yet pressed, until it no longer surpasses (convergence).

The mechanism does not lean on a reliable score: the score only gates
iteration, so same-model evaluation noise barely matters — unlike beam
search, where selection IS the mechanism. ``criteria`` defines what a higher
synthesis is.
"""

import logging
from typing import Any, Optional

from . import agent_runtime
from .agent_factory import create_agent
from .gan_evaluator import (
    DEFAULT_EVALUATION_CRITERIA,
    build_discriminator_instruction,
    parse_verdict,
)
from .generation import parse_list
from .llm_config import get_model_config

logger = logging.getLogger(__name__)

TENSION_PROMPT = """Before solving, judge whether this problem has a genuine dialectical tension — a real trade-off or opposition where a one-sided answer goes wrong.

**Problem:**
{problem}

If there IS such a tension, reply with ONE line:
X vs Y — <one sentence on why this opposition is the crux>
If the problem has a single correct or determinate answer with no real trade-off (a factual, computational, or well-defined technical task), reply with exactly:
NONE"""

THESIS_PROMPT = """Give your single best solution to this problem.

**Problem:**
{problem}

Be concrete and actionable. Provide the solution directly."""

ANTITHESIS_PROMPT = """A solution (the thesis) has been proposed for a problem whose core tension is:

**Core tension:** {tension}

The thesis takes one side of this tension. Do NOT critique the thesis or list its flaws. Become its dialectical opposite: propose {n} COMPLETE alternative solution(s) to the same problem. The first must fully commit to the OTHER side of the core tension above; any further ones oppose along different axes (e.g. simplicity vs power, short- vs long-term, centralize vs distribute).

Each must be a full, standalone rival solution that a smart advocate of the opposite value would genuinely champion and stake their reputation on — a real competing solution, not a comment on the thesis.

**Problem:**
{problem}

**Thesis:**
{thesis}
{prior_block}
Return a numbered list, one self-contained alternative solution per item."""

SYNTHESIS_PROMPT = """You are resolving a dialectic: a thesis and the strongest rival solution(s) to it, around this core tension:

**Core tension:** {tension}

**Problem:**
{problem}

**Thesis (one solution):**
{thesis}

**Antithesis (rival solution{plural} built on opposing principles):**
{antithesis}

Produce a SYNTHESIS that transcends the rivalry: take what is right in the thesis AND in each rival, resolve the tension between their underlying principles, and deliver a solution stronger than any of them alone. Do not pick a winner or staple them together — integrate the conflicting truths into a higher solution that none of them held.

**What makes a synthesis better (judge yourself against this):**
{criteria}

Provide the synthesized solution directly."""


class DialecticEngine:
    """Runs the understand → thesis → antithesis → synthesis spiral."""

    def __init__(
        self,
        problem: str,
        proposer,
        synthesizer,
        discriminator,
        criteria: str = DEFAULT_EVALUATION_CRITERIA,
        max_rounds: int = 3,
        perspectives: int = 1,
    ):
        self.problem = problem
        self.proposer = proposer
        self.synthesizer = synthesizer
        self.discriminator = discriminator
        self.criteria = criteria
        self.max_rounds = max_rounds
        self.perspectives = max(1, perspectives)

    async def _score(self, solution: str) -> float:
        instruction = build_discriminator_instruction(solution, {}, self.criteria)
        return parse_verdict(
            await agent_runtime.run_agent(self.discriminator, instruction)
        ).score

    async def _identify_tension(self) -> str:
        """Name the problem's core contradiction before opposing — the cognitive
        step that makes the dialectic understand the problem, and decide whether
        a dialectic is even warranted.
        """
        return (
            await agent_runtime.run_agent(
                self.proposer, TENSION_PROMPT.format(problem=self.problem)
            )
        ).strip()

    async def _oppose(self, thesis: str, prior: list[str], tension: str) -> list[str]:
        """Surface complete rival solution(s): the first along the core tension,
        later rounds along axes not yet pressed (spiral ascent, not circling).
        """
        if prior:
            prior_block = (
                "\nYou already pressed these oppositions in earlier rounds — do "
                "NOT repeat them; find genuinely different, deeper axes:\n"
                + "\n".join(f"- {a[:200]}" for a in prior)
                + "\n"
            )
        else:
            prior_block = ""
        response = await agent_runtime.run_agent(
            self.proposer,
            ANTITHESIS_PROMPT.format(
                problem=self.problem,
                thesis=thesis,
                n=self.perspectives,
                prior_block=prior_block,
                tension=tension,
            ),
        )
        if self.perspectives == 1:
            return [response.strip()]
        return parse_list(response)[: self.perspectives] or [response.strip()]

    async def _synthesize(
        self, thesis: str, antitheses: list[str], tension: str
    ) -> str:
        if len(antitheses) == 1:
            antithesis_block, plural = antitheses[0], ""
        else:
            antithesis_block = "\n\n".join(
                f"{i}. {a}" for i, a in enumerate(antitheses, 1)
            )
            plural = "s, along different axes"
        return (
            await agent_runtime.run_agent(
                self.synthesizer,
                SYNTHESIS_PROMPT.format(
                    problem=self.problem,
                    thesis=thesis,
                    antithesis=antithesis_block,
                    plural=plural,
                    tension=tension,
                    criteria=self.criteria,
                ),
            )
        ).strip()

    async def run(self) -> dict[str, Any]:
        """Execute the dialectic and return the converged answer + trace."""
        tension = await self._identify_tension()
        logger.info("Core tension: %s", tension)
        thesis = (
            await agent_runtime.run_agent(
                self.proposer, THESIS_PROMPT.format(problem=self.problem)
            )
        ).strip()

        # No genuine tension (factual/determinate): a dialectic would be theater
        # and waste 3-5x the calls. Return the direct solution — knowing when
        # NOT to dialecticize is part of being intelligent.
        if tension.strip().upper().startswith("NONE"):
            logger.info("No dialectical tension; returning the direct solution.")
            return {
                "final_answer": thesis,
                "score": None,
                "rounds": 0,
                "perspectives": self.perspectives,
                "dialecticized": False,
                "history": [
                    {"role": "tension", "round": 0, "text": tension},
                    {"role": "thesis", "round": 0, "text": thesis, "score": None},
                ],
            }

        thesis_score = await self._score(thesis)
        history: list[dict[str, Any]] = [
            {"role": "tension", "round": 0, "text": tension},
            {"role": "thesis", "round": 0, "text": thesis, "score": thesis_score},
        ]
        logger.info("Thesis scored %.1f", thesis_score)

        prior_antitheses: list[str] = []
        for round_num in range(1, self.max_rounds + 1):
            antitheses = await self._oppose(thesis, prior_antitheses, tension)
            prior_antitheses.extend(antitheses)
            synthesis = await self._synthesize(thesis, antitheses, tension)
            synth_score = await self._score(synthesis)

            for a in antitheses:
                history.append({"role": "antithesis", "round": round_num, "text": a})
            history.append(
                {
                    "role": "synthesis",
                    "round": round_num,
                    "text": synthesis,
                    "score": synth_score,
                }
            )
            logger.info(
                "Round %d: synthesis %.1f vs thesis %.1f (%d perspective(s))",
                round_num,
                synth_score,
                thesis_score,
                len(antitheses),
            )

            # Spiral ascent: a synthesis that surpasses the thesis becomes the
            # next thesis; otherwise the dialectic has converged.
            if synth_score <= thesis_score:
                logger.info("Synthesis did not surpass thesis; converged.")
                break
            thesis, thesis_score = synthesis, synth_score

        return {
            "final_answer": thesis,
            "score": thesis_score,
            "rounds": history[-1]["round"],
            "perspectives": self.perspectives,
            "dialecticized": True,
            "history": history,
        }


def create_dialectic_engine(
    problem: str,
    criteria: Optional[str] = None,
    max_rounds: int = 3,
    perspectives: int = 1,
    model_config: Optional[str] = None,
    discriminator_model: Optional[str] = None,
) -> DialecticEngine:
    """Wire a DialecticEngine with default agents (the soul kernel).

    ``perspectives`` widens each round to oppose along that many distinct axes
    (richer synthesis, more calls). ``discriminator_model`` may be stronger,
    but the dialectic is far less sensitive to evaluator quality than beam
    search — the score only gates iteration, it does not select candidates.
    """
    proposer = create_agent(
        role="Generator",
        role_name="Proposer",
        model_config=model_config or get_model_config("GENERATOR"),
    )
    synthesizer = create_agent(
        role="Synthesizer",
        role_name="Synthesizer",
        model_config=model_config or get_model_config("SYNTHESIZER"),
    )
    discriminator = create_agent(
        role="Discriminator",
        role_name="Discriminator",
        model_config=discriminator_model or get_model_config("DISCRIMINATOR"),
        output_schema=None,  # prompt-driven JSON; robust across proxy backends
    )
    return DialecticEngine(
        problem=problem,
        proposer=proposer,
        synthesizer=synthesizer,
        discriminator=discriminator,
        criteria=criteria or DEFAULT_EVALUATION_CRITERIA,
        max_rounds=max_rounds,
        perspectives=perspectives,
    )
