from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ThoughtData(BaseModel):
    """A single node in the Tree of Thoughts."""

    parentId: str | None = Field(None, description="Parent node ID. None for root.")
    thoughtId: str = Field(..., description="Unique node identifier.")
    thought: str = Field(..., min_length=1, description="Core content of the thought.")
    evaluationScore: float | None = Field(None, ge=0, le=10, description="Adversarial score 0-10.")
    status: str = Field("active", description="Node lifecycle status.")
    depth: int = Field(..., ge=0, description="Depth in the tree (root=0).")
    adversarialRounds: int = Field(0, ge=0, description="Number of GAN refinement rounds completed.")
    refinementHistory: list[dict[str, Any]] | None = Field(None, description="Discriminator feedback per round.")

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


def score_of(node: ThoughtData) -> float:
    """None-safe evaluation score for sorting (unscored nodes sort as 0)."""
    return node.evaluationScore if node.evaluationScore is not None else 0.0


class DiscriminatorVerdict(BaseModel):
    """The Discriminator LLM's structured verdict for a single thought.

    Used as an ADK ``output_schema`` so the model returns JSON directly.
    Kept Gemini-structured-output compatible: no ``extra='forbid'`` (which emits
    ``additionalProperties: false``) and no numeric range constraints (which emit
    ``minimum``/``maximum``) — Gemini's response schema rejects both. Range
    clamping is done in code instead.
    """

    score: float = Field(description="Quality score from 0 to 10.")
    flaws: list[str] = Field(default_factory=list, description="Specific issues found.")
    suggestions: list[str] = Field(default_factory=list, description="Actionable improvements.")
    should_terminate: bool = Field(default=False, description="Whether this path should stop.")
    reasoning: str = Field(default="", description="Brief justification for the score.")


class EvaluationResult(BaseModel):
    """Full evaluation record for a thought, assembled by the GAN loop.

    Wraps the Discriminator's verdict with loop-level bookkeeping
    (round counters and per-round history) that the LLM does not produce.
    """

    score: float = Field(..., ge=0, le=10, description="Quality score 0-10.")
    flaws: list[str] = Field(default_factory=list, description="Specific issues found.")
    suggestions: list[str] = Field(default_factory=list, description="Actionable improvements.")
    should_terminate: bool = Field(False, description="Whether this path should stop.")
    reasoning: str = Field("", description="Brief justification for the score.")
    adversarial_rounds: int = Field(0, ge=0, description="Total adversarial rounds completed.")
    history: list[dict[str, Any]] = Field(default_factory=list, description="Evaluation history per round.")
    refined_thought: str = Field("", description="Final thought text the returned score applies to.")

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_verdict(cls, verdict: "DiscriminatorVerdict") -> "EvaluationResult":
        """Build an EvaluationResult from a Discriminator verdict, clamping score to 0-10."""
        return cls(
            score=max(0.0, min(10.0, verdict.score)),
            flaws=verdict.flaws,
            suggestions=verdict.suggestions,
            should_terminate=verdict.should_terminate,
            reasoning=verdict.reasoning,
        )
