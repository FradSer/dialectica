"""Default LLM-backed thought generator and list parsing."""

import logging
import re

from google.adk.agents import LlmAgent

from . import agent_runtime
from .models import ThoughtData

logger = logging.getLogger(__name__)

# Matches a numbered (1. / 1)) or bulleted (-, *, •) list-item start.
_ITEM_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.*)$")


def parse_list(response: str) -> list[str]:
    """Parse a numbered/bulleted list from an agent response.

    Continuation lines are accumulated into the current item, so multi-line
    entries keep their full body (a generator often emits a bold header
    followed by a description on the next lines). Supports ``1.``, ``1)``,
    ``-``, ``*`` and ``•`` markers; falls back to one-item-per-line.
    """
    items: list[list[str]] = []
    for raw in response.strip().splitlines():
        if not raw.strip():
            continue
        match = _ITEM_MARKER.match(raw)
        if match:
            items.append([match.group(1).strip()])
        elif items:
            items[-1].append(raw.strip())

    parsed = [" ".join(parts).strip() for parts in items]
    parsed = [p for p in parsed if p]
    if parsed:
        return parsed

    return [line.strip() for line in response.strip().splitlines() if line.strip()]


DEFAULT_STRATEGY_PROMPT = """Generate 3-5 distinct initial strategies to solve this problem:

**Problem:**
{problem}

**Requirements:**
- Each strategy should represent a fundamentally different approach
- Be specific and actionable
- Consider different perspectives and trade-offs

**Output Format:**
Return a FLAT numbered list — one strategy per line, starting with "1. ", "2. ", etc.
Each strategy is a single self-contained line. Do NOT use sub-bullets, nested
lists, headings, code blocks, or multi-paragraph explanations.
"""

DEFAULT_CHILD_PROMPT = """Generate 2-4 specific next steps or refinements for this thought:

**Parent Thought:**
{parent}

**Context:**
- Problem: {problem}
- Depth: {depth}

**Requirements:**
- Each child should be a concrete step forward
- Build on the parent thought, don't just restate it
- Consider different angles or sub-problems

**Output Format:**
Return a FLAT numbered list — one child thought per line, starting with "1. ", "2. ", etc.
Each item is a single self-contained line. Do NOT use sub-bullets, nested lists,
headings, code blocks, or multi-paragraph explanations.
"""


class LlmGenerator:
    """Generates thoughts via an LlmAgent and configurable prompt templates.

    Implements the ``Generator`` protocol. Swap the agent, the strategy prompt,
    or the child prompt to retarget the engine at a different kind of problem.
    """

    def __init__(
        self,
        agent: LlmAgent,
        strategy_prompt: str = DEFAULT_STRATEGY_PROMPT,
        child_prompt: str = DEFAULT_CHILD_PROMPT,
        max_items: int = 8,
    ):
        self.agent = agent
        self.strategy_prompt = strategy_prompt
        self.child_prompt = child_prompt
        # Explicit branching-factor bound: at most this many candidates per
        # expansion, regardless of how many the model emits.
        self.max_items = max_items

    async def expand(self, parent: ThoughtData, problem: str) -> list[str]:
        if parent.depth == 0:
            instruction = self.strategy_prompt.format(problem=problem)
        else:
            instruction = self.child_prompt.format(
                problem=problem, parent=parent.thought, depth=parent.depth
            )
        response = await agent_runtime.run_agent(self.agent, instruction)
        return parse_list(response)[: self.max_items]
