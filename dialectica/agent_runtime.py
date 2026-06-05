"""Single entry point for invoking an LlmAgent.

Centralizing the ADK Runner call gives every pluggable component (generator,
evaluator, synthesizer) one shared seam — which is also the one place tests
patch to run the engine without the network.
"""

import logging

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner

logger = logging.getLogger(__name__)


async def run_agent(agent: LlmAgent, instruction: str) -> str:
    """Run ``agent`` on ``instruction`` and return its concatenated text output."""
    runner = InMemoryRunner(agent=agent, app_name="dialectica")
    events = await runner.run_debug(instruction, quiet=True)

    response_text = ""
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not part.thought:
                    response_text += part.text

    return response_text.strip()
