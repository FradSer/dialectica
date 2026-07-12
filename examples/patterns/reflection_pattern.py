"""Canonical open-ended recipe: heterogeneous multi-angle reflection.

Gather (parallel angles) → Frame (core tension) → Critique → Synthesize.
Each gather angle may use a different model from a heterogeneous roster —
the measured lever for open-ended meta-tasks (README Evaluation #6 / #7).

NOT shipped API — composed on ``Workflow`` / ``agent(model=...)``. Measured:
**5-0-0** vs single and vs homo on meta; **10-0-0** vs single on meta+default.
Roster heterogeneity is the lever; LLM float scorers / AB-MCTS / extra
adversarial stages add no consistent lift (see ``quality_workflow_pattern``).

Prefer this over ``create_quality_workflow_engine`` unless comparing modes.

Reproduce: ``uv run python -m evals.reflection_ablation``
             ``uv run python -m evals.quality_workflow_ablation``

ACCESS-LIST MODE (``use_access_lists=True``): instead of inlining prior-stage
outputs into each stage's prompt via ``.format()``, critique and synthesize
pull their prior context through the kernel ``agent(sees=[...])`` primitive
(Fugu-Ultra-style selective visibility): each critique sees *only* its own
gather angle, and synthesize sees the tension + the set of critiques — never
the full transcript. This is structurally cleaner (shorter task prompts,
kernel-enforced isolation) and exercises ``sees=`` on a shipped-recipe code
path; the measured results above were taken with inlined prompts, so this mode
is opt-in until an ablation shows it lifts or ties on the same matrices.
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

# Access-list variant: the gather angle's output arrives via agent(sees=...),
# so the prompt names it as prior context rather than inlining it. Mirrors
# CRITIQUE_PROMPT minus the ANALYSIS block.
CRITIQUE_PROMPT_SEES = """Critique the prior-context analysis of this problem. \
Be the smartest skeptic in the room:
- Name the single most important concrete thing this analysis gets WRONG or LEAVES OUT.
- State the one question a decision-maker would ask that this analysis cannot answer.
- State the ONE specific contrarian position a stronger final answer MUST defend \
taking (the unpopular-but-correct call the analysis avoided).
- Give the specific correction the synthesis MUST make to not repeat this flaw.

PROBLEM:
{problem}

The analysis to critique is in the prior context above."""

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

# Access-list variant: tension + critiques arrive via agent(sees=[...]) as
# prior context, so the prompt references them there rather than inlining.
SYNTHESIZE_PROMPT_SEES = """You are the lead decision-maker. Write the final answer to:
{problem}

The core tension and the critiques are in the prior context above. Your \
synthesis must be BETTER than a single expert's first pass: concrete, \
specific, actionable, and free of generic consultant prose.

Rules:
- Pick ONE binding decision and commit to it. Do NOT enumerate every option — \
  a single-pass answer already does that. Yours wins by sharpness, not coverage.
- Lead with the single sharpest recommendation and the precise trigger that \
  decides it (a measurable condition, not 'when ready').
- Resolve the core tension explicitly: name the condition under which each side wins, \
  and make a decisive recommendation for THIS problem's context.
- Name the non-obvious failure mode a naive answer misses — the one the critiques \
  flagged — and how this answer structurally avoids it.
- Carry forward the specific numbers, sequencing, and trade-offs from the prior \
  context; do NOT abstract them into vagueness."""


def _default_angle_models(roster: list[str]) -> dict[str, str]:
    """Map each angle to a roster member via round-robin."""
    if not roster:
        raise ValueError("roster must contain at least one model config")
    return {angle: roster[i % len(roster)] for i, angle in enumerate(DEFAULT_ANGLES)}


def _model_key(model: Any) -> str:
    """Normalize a model config string or LiteLlm instance to a hashable key."""
    if isinstance(model, str):
        return model
    litellm_model = getattr(model, "model", None)
    if litellm_model:
        return str(litellm_model)
    return repr(model)


def _is_heterogeneous(
    angle_models: dict[str, Any],
    frame_model: Any,
    critique_model: Any,
    synthesize_model: Any,
) -> bool:
    keys = {_model_key(v) for v in angle_models.values()}
    keys.update(_model_key(m) for m in (frame_model, critique_model, synthesize_model))
    return len(keys) > 1


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
        use_access_lists: bool = False,
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
        # When True, critique/synthesize pull prior-stage outputs through the
        # kernel agent(sees=[...]) primitive (Fugu-Ultra-style selective
        # visibility) instead of inlining them via .format(). See module
        # docstring for why this is opt-in.
        self.use_access_lists = use_access_lists

    async def run(self) -> dict[str, Any]:
        """Execute gather → frame → critique → synthesize and return trace + answer."""
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
                    for a in self.angles
                ]
            )
            findings: list[str] = []
            # (gather label, finding text) pairs so the access-list critique
            # can name its producer via sees=["g_<angle>"].
            labeled_findings: list[tuple[str, str]] = []
            for angle, text in zip(self.angles, findings_raw, strict=True):
                if text:
                    findings.append(text)
                    labeled_findings.append((f"g_{angle}", text))
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
            if self.use_access_lists:
                # Each critique sees ONLY its own gather angle's output via
                # the kernel sees= primitive — selective visibility, not a
                # full transcript dump (Fugu-Ultra anti-collapse).
                critiques_raw = await wf.pipeline(
                    labeled_findings,
                    lambda lf, _, i: wf.agent(
                        CRITIQUE_PROMPT_SEES.format(problem=self.problem),
                        model=self.critique_model,
                        label=f"c_{i}",
                        sees=[lf[0]],
                    ),
                )
            else:
                critiques_raw = await wf.pipeline(
                    labeled_findings,
                    lambda lf, _, i: wf.agent(
                        CRITIQUE_PROMPT.format(problem=self.problem, analysis=lf[1]),
                        model=self.critique_model,
                        label=f"c_{i}",
                    ),
                )
            critiques: list[str] = []
            critique_labels: list[str] = []
            for i, text in enumerate(critiques_raw):
                if text:
                    critiques.append(text)
                    critique_labels.append(f"c_{i}")
                    history.append(
                        {
                            "stage": "critique",
                            "label": f"c_{i}",
                            "model": self.critique_model,
                            "text": text,
                        }
                    )

            wf.phase("Synthesize")
            if self.use_access_lists:
                # Synthesize sees the tension + every critique's output via
                # sees= — gathered analyses remain visible through the
                # critiques that reference them, but the raw gather
                # transcripts are not re-injected, preserving the
                # selective-visibility discipline.
                final = (
                    await wf.agent(
                        SYNTHESIZE_PROMPT_SEES.format(problem=self.problem),
                        model=self.synthesize_model,
                        label="synth",
                        sees=["tension", *critique_labels],
                    )
                ).strip()
            else:
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
    use_access_lists: bool = False,
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

    Set ``use_access_lists=True`` to route critique/synthesize prior context
    through the kernel ``agent(sees=[...])`` primitive (Fugu-Ultra-style
    selective visibility) instead of inlining via ``.format()``. Opt-in: the
    measured results were taken with inlined prompts.
    """
    return ReflectionEngine(
        problem,
        roster=roster,
        angle_models=angle_models,
        frame_model=frame_model,
        critique_model=critique_model,
        synthesize_model=synthesize_model,
        angles=angles,
        use_access_lists=use_access_lists,
    )
