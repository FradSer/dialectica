"""Reference pattern: heterogeneous multi-angle reflection workflow.

Gather (parallel angles) → Frame (core tension) → Critique → Synthesize.
Each gather angle may use a different model from a heterogeneous roster —
the measured lever for open-ended meta-tasks (see README Evaluation finding
#5 and ``evals/reflection_ablation.py``).

NOT shipped API. Prior ensemble work showed that on open-ended tasks
**roster heterogeneity** improves robustness vs a prompt-matched single call,
while an LLM float scorer / AB-MCTS scheduling signal adds no measurable lift
over blind-pick. This pattern captures the honest version: parallel independent
models + structured critique + synthesis — no scorer, no bandit.

Reproduce: ``uv run python -m evals.reflection_ablation``
"""

import logging
from typing import Any

from dialectica import Workflow
from dialectica import workflow as wf

logger = logging.getLogger(__name__)

DEFAULT_ROSTER: list[str] = ["openai:qwen3.6-flash", "openai:glm-5.2"]
DEFAULT_ANGLES: list[str] = [
    "broad",
    "critical",
    "practitioner",
    "stakeholder-opposition",
]

GATHER_PROMPT = """Analyze this problem from a {angle} angle. Be concrete and actionable:
- Name the single most important decision this angle forces.
- Give ONE concrete number, threshold, or magnitude that anchors it \
(cost, headcount, time, rate — a real figure, not 'significant').
- State the ONE trade-off a naive answer would hand-wave.

PROBLEM:
{problem}"""

FRAME_PROMPT = """What is the single core tension or trade-off in this problem — the \
opposition a one-sided answer would resolve wrongly? One sentence.

PROBLEM:
{problem}"""

CRITIQUE_PROMPT = """Critique this analysis of the problem. Be the smartest skeptic in the room:
- Name the single most important concrete thing this analysis gets WRONG or LEAVES OUT.
- State the one question a decision-maker would ask that this analysis cannot answer.
- State the ONE specific contrarian position a stronger final answer MUST defend \
taking (the unpopular-but-correct call the analysis avoided).
- Give the specific correction the synthesis MUST make to not repeat this flaw.

PROBLEM:
{problem}

ANALYSIS:
{analysis}"""

SYNTHESIZE_PROMPT = """You are the lead decision-maker. Write the final answer to:
{problem}

CORE TENSION (your answer must resolve this, not pick a side naively):
{tension}

You have angle analyses and their critiques. Your synthesis must be \
BETTER than a single expert's first pass: concrete, specific, actionable, and \
free of generic consultant prose.

Rules:
- Pick ONE binding decision and commit to it. Do NOT enumerate every option — \
  a single-pass answer already does that. Yours wins by sharpness, not coverage.
- Lead with the single sharpest recommendation and the precise trigger that \
  decides it (a measurable condition, not 'when ready').
- Resolve the core tension explicitly: name the condition under which each side wins, \
  and make a decisive recommendation for THIS problem's context.
- Name the non-obvious failure mode a naive answer misses — the one the critiques \
  flagged — and how this answer structurally avoids it.
- Carry forward the specific numbers, sequencing, and trade-offs from the analyses; \
  do NOT abstract them into vagueness.

ANALYSES:
{findings}

CRITIQUES (address the weaknesses, do not repeat them):
{critiques}"""


def _default_angle_models(roster: list[str]) -> dict[str, str]:
    """Map each angle to a roster member via round-robin."""
    if not roster:
        raise ValueError("roster must contain at least one model config")
    return {angle: roster[i % len(roster)] for i, angle in enumerate(DEFAULT_ANGLES)}


def _is_heterogeneous(
    angle_models: dict[str, str],
    frame_model: str,
    critique_model: str,
    synthesize_model: str,
) -> bool:
    models = set(angle_models.values()) | {
        frame_model,
        critique_model,
        synthesize_model,
    }
    return len(models) > 1


class ReflectionEngine:
    """Multi-angle reflection workflow with optional per-stage model assignment."""

    def __init__(
        self,
        problem: str,
        *,
        roster: list[str] | None = None,
        angle_models: dict[str, str] | None = None,
        frame_model: str | None = None,
        critique_model: str | None = None,
        synthesize_model: str | None = None,
        angles: list[str] | None = None,
    ):
        self.problem = problem
        self.angles = angles if angles is not None else list(DEFAULT_ANGLES)
        resolved_roster = list(roster if roster is not None else DEFAULT_ROSTER)
        if angle_models is None:
            self.angle_models = _default_angle_models(resolved_roster)
        else:
            self.angle_models = dict(angle_models)
        self.frame_model = frame_model or resolved_roster[0]
        self.critique_model = (
            critique_model
            or self.angle_models.get("critical")
            or (resolved_roster[1] if len(resolved_roster) > 1 else resolved_roster[0])
        )
        self.synthesize_model = synthesize_model or resolved_roster[-1]
        self.heterogeneous = _is_heterogeneous(
            self.angle_models,
            self.frame_model,
            self.critique_model,
            self.synthesize_model,
        )

    async def run(self) -> dict[str, Any]:
        """Execute gather → frame → critique → synthesize and return trace + answer."""
        history: list[dict[str, Any]] = []

        async def script() -> str:
            wf.phase("Gather")
            findings_raw = await wf.parallel(
                [
                    (lambda a=a: wf.agent(
                        GATHER_PROMPT.format(angle=a, problem=self.problem),
                        model=self.angle_models[a],
                        label=f"g_{a}",
                    ))
                    for a in self.angles
                ]
            )
            findings: list[str] = []
            for angle, text in zip(self.angles, findings_raw, strict=True):
                if text:
                    findings.append(text)
                    history.append(
                        {
                            "stage": "gather",
                            "label": f"g_{angle}",
                            "model": self.angle_models[angle],
                            "text": text,
                        }
                    )

            wf.phase("Frame")
            tension = (
                await wf.agent(
                    FRAME_PROMPT.format(problem=self.problem),
                    model=self.frame_model,
                    label="tension",
                )
            ).strip()
            history.append(
                {
                    "stage": "frame",
                    "label": "tension",
                    "model": self.frame_model,
                    "text": tension,
                }
            )

            wf.phase("Critique")
            critiques_raw = await wf.pipeline(
                findings,
                lambda f, _, i: wf.agent(
                    CRITIQUE_PROMPT.format(problem=self.problem, analysis=f),
                    model=self.critique_model,
                    label=f"c_{i}",
                ),
            )
            critiques: list[str] = []
            for i, text in enumerate(critiques_raw):
                if text:
                    critiques.append(text)
                    history.append(
                        {
                            "stage": "critique",
                            "label": f"c_{i}",
                            "model": self.critique_model,
                            "text": text,
                        }
                    )

            wf.phase("Synthesize")
            final = (
                await wf.agent(
                    SYNTHESIZE_PROMPT.format(
                        problem=self.problem,
                        tension=tension,
                        findings="\n\n".join(findings),
                        critiques="\n\n".join(critiques),
                    ),
                    model=self.synthesize_model,
                    label="synth",
                )
            ).strip()
            history.append(
                {
                    "stage": "synthesize",
                    "label": "synth",
                    "model": self.synthesize_model,
                    "text": final,
                }
            )
            return final

        final_answer = await Workflow(script).run()
        logger.info(
            "Reflection complete (heterogeneous=%s, stages=%d)",
            self.heterogeneous,
            len(history),
        )
        return {
            "final_answer": final_answer,
            "history": history,
            "heterogeneous": self.heterogeneous,
        }


def create_reflection_engine(
    problem: str,
    *,
    roster: list[str] | None = None,
    angle_models: dict[str, str] | None = None,
    frame_model: str | None = None,
    critique_model: str | None = None,
    synthesize_model: str | None = None,
    angles: list[str] | None = None,
) -> ReflectionEngine:
    """Wire a ReflectionEngine for open-ended multi-angle reflection.

    Pass a heterogeneous ``roster`` (or explicit ``angle_models``) so each gather
    angle uses a different model. For homogeneous mode — same pipeline, one model
    — set every stage to the same config, e.g.::

        create_reflection_engine(
            problem,
            angle_models={a: MODEL for a in DEFAULT_ANGLES},
            frame_model=MODEL,
            critique_model=MODEL,
            synthesize_model=MODEL,
        )
    """
    return ReflectionEngine(
        problem,
        roster=roster,
        angle_models=angle_models,
        frame_model=frame_model,
        critique_model=critique_model,
        synthesize_model=synthesize_model,
        angles=angles,
    )
