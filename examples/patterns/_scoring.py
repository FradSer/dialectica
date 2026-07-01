"""Shared discriminator-style scoring helper for the dialectic and ToT+GAN
reference patterns.

Both patterns need an LLM verdict (a 0-10 score plus flaws/suggestions/
should_terminate) on a candidate thought. Rather than reimplementing
``gan_evaluator.py``'s retry/circuit-breaker machinery, both call
``wf.agent(prompt, schema=Verdict, ...)`` and get ``workflow.py``'s own
fence/escape-repair and re-ask-on-parse-failure for free.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _coerce_str_list(value: Any) -> Any:
    """Coerce list items to strings so object-valued flaws/suggestions parse.

    Models frequently return flaws/suggestions as objects (e.g.
    ``{"category": "Feasibility", "text": "..."}``) instead of plain strings.
    Left as-is that fails ``list[str]`` validation, silently degrading the
    verdict to ``clamp_score(None) == 0.0`` on every retry. Pull out the
    human-readable text (or flatten the object) instead of losing the verdict.
    """
    if not isinstance(value, list):
        return value
    coerced: list[str] = []
    for item in value:
        if isinstance(item, str):
            coerced.append(item)
        elif isinstance(item, dict):
            text = (
                item.get("text")
                or item.get("description")
                or item.get("flaw")
                or item.get("issue")
                or item.get("suggestion")
            )
            coerced.append(
                str(text) if text else "; ".join(f"{k}: {v}" for k, v in item.items())
            )
        else:
            coerced.append(str(item))
    return coerced


class Verdict(BaseModel):
    """An LLM's structured judgment of a single candidate thought.

    Kept Gemini-structured-output compatible: no ``extra="forbid"`` (which
    emits ``additionalProperties: false``) and no numeric range constraints
    (which emit ``minimum``/``maximum``) — Gemini's response schema rejects
    both. Range clamping happens in the caller instead.
    """

    score: float = Field(description="Quality score from 0 to 10.")
    flaws: list[str] = Field(default_factory=list, description="Specific issues found.")
    suggestions: list[str] = Field(
        default_factory=list, description="Actionable improvements."
    )
    should_terminate: bool = Field(
        default=False, description="Whether this path should stop."
    )
    reasoning: str = Field(default="", description="Brief justification for the score.")

    _coerce_lists = field_validator("flaws", "suggestions", mode="before")(
        _coerce_str_list
    )


DEFAULT_CRITERIA = """\
1. **Soundness**: Is the thought logically sound and feasible?
2. **Completeness**: Does it address the problem adequately?
3. **Feasibility under stated constraints**: Does it respect the problem's
   explicit constraints (budget, team size, timeline, politics)? Penalize
   complexity that the stated actors could not realistically execute.
4. **Practicality**: Can it be implemented effectively with the means at hand?
   Prefer simple, executable steps over clever but fragile ones."""


def build_scoring_prompt(
    thought: str, context: dict, criteria: str = DEFAULT_CRITERIA
) -> str:
    ctx_lines = "\n".join(f"- {k}: {v}" for k, v in context.items() if v)
    return f"""Evaluate the following thought critically:

**Thought:**
{thought}

**Context:**
{ctx_lines}

**Evaluation Criteria:**
{criteria}

Score the thought from 0 to 10, list specific flaws and actionable suggestions,
give a brief reasoning, and set should_terminate to true only if the path is
fundamentally flawed. Be rigorous but constructive.

Return your verdict as a single JSON object."""


def clamp_score(verdict: Verdict | None) -> float:
    """None-safe, range-clamped score extraction (a parse failure scores 0)."""
    if verdict is None:
        return 0.0
    return max(0.0, min(10.0, verdict.score))
