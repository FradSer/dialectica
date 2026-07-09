"""Reference pattern: multi-model quality workflow mode switcher.

Ablation harness over the same heterogeneous roster. Prefer
``create_reflection_engine`` for production recipes — that is the canonical
open-ended path (README Evaluation #6 / #7).

Modes (each is ``workflow.py`` primitives + per-stage ``model=``):

- **reflection** (default) — delegates to ``reflection_pattern``; measured
  **10-0-0** vs single on meta+default.
- **adversarial** — reflection through critique, then a rival-model complete
  opposing solution. Finding #7: **2-0-8** vs hetero reflection (no consistent
  lift).
- **dialectic** — one-round hetero thesis → antithesis → synthesis (no LLM
  scorer). Finding #7: **0-1-9** vs hetero reflection (NET −1).

NOT shipped API. Use this module to compare compositions; default callers
should import ``create_reflection_engine`` instead.

Reproduce: ``uv run python -m evals.quality_workflow_ablation``
"""

import logging
from typing import Any, Literal

from dialectica import Workflow
from dialectica import workflow as wf
from examples.patterns._scoring import DEFAULT_CRITERIA
from examples.patterns.dialectic_pattern import (
    ANTITHESIS_PROMPT,
    DIALECTIC_PROPOSER_CONTEXT,
    SYNTHESIS_PROMPT,
    TENSION_PROMPT,
    THESIS_PROMPT,
)
from examples.patterns.reflection_pattern import (
    CRITIQUE_PROMPT,
    DEFAULT_ANGLES,
    DEFAULT_ROSTER,
    FRAME_PROMPT,
    GATHER_PROMPT,
    _default_angle_models,
    _is_heterogeneous,
    _model_key,
    create_reflection_engine,
)

logger = logging.getLogger(__name__)

QualityMode = Literal["reflection", "adversarial", "dialectic"]

RIVAL_PROMPT = """The core tension in this problem is:

{tension}

Propose ONE COMPLETE alternative solution that fully commits to the OTHER side
of this tension — a solution a smart advocate of the opposite value would
champion. Do NOT critique existing analyses; deliver a standalone rival answer.

**Problem:**
{problem}

Be concrete, specific, and actionable — numbers, thresholds, sequencing."""

SYNTHESIZE_ADVERSARIAL_PROMPT = """You are the lead decision-maker. Write the final answer to:
{problem}

CORE TENSION (resolve this, not pick a side naively):
{tension}

You have angle analyses, their critiques, AND a complete rival solution from
the opposite side of the tension. Your synthesis must DOMINATE a single expert
first pass: pick ONE binding decision, lead with the sharpest recommendation,
resolve the tension with a measurable trigger, and structurally avoid the
failure modes the critiques flagged.

ANALYSES:
{findings}

CRITIQUES:
{critiques}

RIVAL SOLUTION (opposite side of the tension):
{rival}
"""


def _stage_models(roster: list[str]) -> dict[str, str]:
    """Default per-stage model map for a heterogeneous roster."""
    if len(roster) < 2:
        m = roster[0]
        return {
            "frame": m,
            "critique": m,
            "rival": m,
            "thesis": m,
            "antithesis": m,
            "synthesize": m,
        }
    return {
        "frame": roster[0],
        "critique": roster[1],
        "rival": roster[1],
        "thesis": roster[0],
        "antithesis": roster[1],
        "synthesize": roster[-1],
    }


class QualityWorkflowEngine:
    """Multi-model quality workflow with selectable composition mode."""

    def __init__(
        self,
        problem: str,
        mode: QualityMode = "reflection",
        *,
        roster: list[str] | None = None,
    ):
        self.problem = problem
        self.mode = mode
        self.roster = list(roster if roster is not None else DEFAULT_ROSTER)
        self.angle_models = _default_angle_models(self.roster)
        self.stages = _stage_models(self.roster)
        self.heterogeneous = _is_heterogeneous(
            self.angle_models,
            self.stages["frame"],
            self.stages["critique"],
            self.stages["synthesize"],
        )

    async def run(self) -> dict[str, Any]:
        if self.mode == "reflection":
            engine = create_reflection_engine(
                self.problem,
                roster=self.roster,
            )
            result = await engine.run()
            result["mode"] = self.mode
            return result

        if self.mode == "adversarial":
            return await self._run_adversarial()
        return await self._run_dialectic()

    async def _run_adversarial(self) -> dict[str, Any]:
        history: list[dict[str, Any]] = []

        async def script() -> str:
            wf.phase("Gather")
            findings_raw = await wf.parallel(
                [
                    (
                        lambda a=a: wf.agent(
                            GATHER_PROMPT.format(angle=a, problem=self.problem),
                            model=self.angle_models[a],
                            label=f"g_{a}",
                        )
                    )
                    for a in DEFAULT_ANGLES
                ]
            )
            findings = [t for t in findings_raw if t]

            wf.phase("Frame")
            tension = (
                await wf.agent(
                    FRAME_PROMPT.format(problem=self.problem),
                    model=self.stages["frame"],
                    label="tension",
                )
            ).strip()

            wf.phase("Critique")
            critiques_raw = await wf.pipeline(
                findings,
                lambda f, _, i: wf.agent(
                    CRITIQUE_PROMPT.format(problem=self.problem, analysis=f),
                    model=self.stages["critique"],
                    label=f"c_{i}",
                ),
            )
            critiques = [c for c in critiques_raw if c]

            wf.phase("Rival")
            rival = (
                await wf.agent(
                    RIVAL_PROMPT.format(tension=tension, problem=self.problem),
                    model=self.stages["rival"],
                    label="rival",
                )
            ).strip()
            history.append(
                {
                    "stage": "rival",
                    "label": "rival",
                    "model": self.stages["rival"],
                    "text": rival,
                }
            )

            wf.phase("Synthesize")
            final = (
                await wf.agent(
                    SYNTHESIZE_ADVERSARIAL_PROMPT.format(
                        problem=self.problem,
                        tension=tension,
                        findings="\n\n".join(findings),
                        critiques="\n\n".join(critiques),
                        rival=rival,
                    ),
                    model=self.stages["synthesize"],
                    label="synth",
                )
            ).strip()
            return final

        final_answer = await Workflow(script).run()
        return {
            "final_answer": final_answer,
            "history": history,
            "heterogeneous": self.heterogeneous,
            "mode": self.mode,
        }

    async def _run_dialectic(self) -> dict[str, Any]:
        history: list[dict[str, Any]] = []
        criteria = DEFAULT_CRITERIA

        async def script() -> str:
            wf.phase("Tension")
            tension = (
                await wf.agent(
                    TENSION_PROMPT.format(problem=self.problem),
                    model=self.stages["thesis"],
                    instructions=DIALECTIC_PROPOSER_CONTEXT,
                    label="tension",
                )
            ).strip()
            history.append(
                {
                    "stage": "tension",
                    "label": "tension",
                    "model": self.stages["thesis"],
                    "text": tension,
                }
            )

            if tension.strip().upper().startswith("NONE"):
                thesis = (
                    await wf.agent(
                        THESIS_PROMPT.format(problem=self.problem, criteria=criteria),
                        model=self.stages["thesis"],
                        instructions=DIALECTIC_PROPOSER_CONTEXT,
                        label="thesis",
                    )
                ).strip()
                return thesis

            wf.phase("Thesis")
            thesis = (
                await wf.agent(
                    THESIS_PROMPT.format(problem=self.problem, criteria=criteria),
                    model=self.stages["thesis"],
                    instructions=DIALECTIC_PROPOSER_CONTEXT,
                    label="thesis",
                )
            ).strip()

            wf.phase("Antithesis")
            antithesis = (
                await wf.agent(
                    ANTITHESIS_PROMPT.format(
                        problem=self.problem,
                        thesis=thesis,
                        n=1,
                        prior_block="",
                        tension=tension,
                        criteria=criteria,
                        delimiter="===NEXT===",
                    ),
                    model=self.stages["antithesis"],
                    instructions=DIALECTIC_PROPOSER_CONTEXT,
                    label="antithesis",
                )
            ).strip()

            wf.phase("Synthesize")
            final = (
                await wf.agent(
                    SYNTHESIS_PROMPT.format(
                        problem=self.problem,
                        thesis=thesis,
                        antithesis=antithesis,
                        plural="",
                        tension=tension,
                        criteria=criteria,
                    ),
                    model=self.stages["synthesize"],
                    label="synth",
                )
            ).strip()
            history.extend(
                [
                    {
                        "stage": "thesis",
                        "label": "thesis",
                        "model": self.stages["thesis"],
                        "text": thesis,
                    },
                    {
                        "stage": "antithesis",
                        "label": "antithesis",
                        "model": self.stages["antithesis"],
                        "text": antithesis,
                    },
                    {
                        "stage": "synthesize",
                        "label": "synth",
                        "model": self.stages["synthesize"],
                        "text": final,
                    },
                ]
            )
            return final

        final_answer = await Workflow(script).run()
        return {
            "final_answer": final_answer,
            "history": history,
            "heterogeneous": self.heterogeneous,
            "mode": self.mode,
        }


def create_quality_workflow_engine(
    problem: str,
    mode: QualityMode = "reflection",
    *,
    roster: list[str] | None = None,
) -> QualityWorkflowEngine:
    """Wire a multi-model quality workflow for mode comparison / ablation.

    For the default open-ended recipe, prefer ``create_reflection_engine`` —
    ``mode="reflection"`` here only delegates to it. ``adversarial`` /
    ``dialectic`` are kept for ``evals/quality_workflow_ablation.py``; finding
    #7 found no consistent lift over hetero reflection.
    """
    return QualityWorkflowEngine(problem, mode, roster=roster)


def roster_model_keys(roster: list[str]) -> list[str]:
    """Expose normalized roster keys for eval reporting."""
    return [_model_key(m) for m in roster]
