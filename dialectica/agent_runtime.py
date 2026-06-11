"""Single entry point for invoking an LlmAgent.

Centralizing the ADK Runner call gives every pluggable component (generator,
evaluator, synthesizer) one shared seam — which is also the one place tests
patch to run the engine without the network.

``run_agent`` retries transient failures with exponential backoff: an engine
run is hundreds of sequential LLM calls, and without retry a single network
error or rate limit throws the whole run away. Persistent failures re-raise.
"""

import asyncio
import logging

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner

logger = logging.getLogger(__name__)


async def _call_agent_once(agent: LlmAgent, instruction: str) -> str:
    """One raw ADK invocation, returning the concatenated text output."""
    runner = InMemoryRunner(agent=agent, app_name="dialectica")
    events = await runner.run_debug(instruction, quiet=True)

    response_text = ""
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not part.thought:
                    response_text += part.text

    return response_text.strip()


async def run_agent(
    agent: LlmAgent,
    instruction: str,
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> str:
    """Run ``agent`` on ``instruction``, retrying transient failures."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await _call_agent_once(agent, instruction)
        except Exception as e:
            if attempt == max_attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            logger.warning(
                "Agent call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                max_attempts,
                delay,
                e,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")
