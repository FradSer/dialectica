"""Default LLM-backed synthesizer (the ``Synthesizer`` protocol)."""

import logging

from google.adk.agents import LlmAgent

from . import agent_runtime
from .models import ThoughtData, score_of

logger = logging.getLogger(__name__)

DEFAULT_SYNTHESIS_PROMPT = """Synthesize a comprehensive solution from the following high-quality thoughts:

**Original Problem:**
{problem}

**Top Thoughts:**
{thoughts}

**Your Task:**
1. Identify common themes and complementary insights
2. Resolve any conflicts between different approaches
3. Create a coherent, actionable solution
4. Structure the answer clearly with sections if appropriate

**Output:**
Provide the synthesized solution directly, without additional commentary.
"""

_NO_THOUGHTS = "Unable to generate sufficient high-quality thoughts for synthesis."


class LlmSynthesizer:
    """Combines the top-scoring thoughts into a final answer via an LlmAgent."""

    def __init__(
        self,
        agent: LlmAgent,
        prompt: str = DEFAULT_SYNTHESIS_PROMPT,
        top_k: int = 10,
    ):
        self.agent = agent
        self.prompt = prompt
        self.top_k = top_k

    async def synthesize(self, problem: str, thoughts: list[ThoughtData]) -> str:
        scored = [t for t in thoughts if t.evaluationScore is not None]
        scored.sort(key=score_of, reverse=True)
        top = scored[: self.top_k]
        if not top:
            return _NO_THOUGHTS

        thoughts_text = "\n\n".join(
            f"**Thought (Score: {t.evaluationScore}/10):**\n{t.thought}" for t in top
        )
        instruction = self.prompt.format(problem=problem, thoughts=thoughts_text)
        response = await agent_runtime.run_agent(self.agent, instruction)
        return response.strip()
