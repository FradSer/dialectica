"""Agentic engine — the one engine that adds CAPABILITY a single forward pass
lacks, not just quality.

The evals settled it: on self-contained prompts, no reasoning scaffold (ToT,
dialectic, repair) beats a well-prompted single call — the model does the task
in one pass, so rearranging its thinking adds nothing. An engine only wins when
it lets the model do something one forward pass *cannot*: act on the world,
observe the result, and iterate — over many steps, across files and state.

This engine is that loop. Given a task and a set of injected tools (read a file,
run the tests, query a service, ...), it runs a tool-using agent: the model
plans, calls a tool, reads the result, and continues until the task is done.
ADK executes the tool-call loop internally, so this is a thin, honest wiring of
``task + tools -> a tool-equipped agent``. The tools are injected by the
consuming app, so the engine stays task-agnostic; the win over a single call is
the information and side effects the tools provide, which one pass never has.
"""

import logging
from typing import Any, Optional

from google.adk.agents import LlmAgent

from . import agent_runtime
from .llm_config import get_model_config

logger = logging.getLogger(__name__)

AGENTIC_SYSTEM_PROMPT = """You are a capable agent that completes a task by USING TOOLS, not by guessing.

How to work:
- Plan briefly, then act: call a tool, read its result, and decide the next step from what you actually observe.
- Never assume a file's contents, a command's output, or that the task is done — verify with the tools.
- Iterate: if a check fails, use the failure to fix the cause, then re-check. Repeat until the task genuinely passes.
- Stop when the task's success condition is objectively met (or you are certain it cannot be), then state the outcome plainly.

{instructions}"""


class AgenticEngine:
    """Runs a tool-using agent on a task; the injected tools do the acting."""

    def __init__(self, task: str, agent: LlmAgent):
        self.task = task
        self.agent = agent

    async def run(self) -> dict[str, Any]:
        """Execute the agent (ADK drives the tool-call loop) and return the result.

        Side effects (file edits, etc.) happen through the tools, so the caller
        checks the objective outcome (e.g. run the tests) after this returns.
        """
        answer = await agent_runtime.run_agent(self.agent, self.task)
        return {"final_answer": answer}


def create_agentic_engine(
    task: str,
    tools: list,
    model_config: Optional[str] = None,
    instructions: str = "",
) -> AgenticEngine:
    """Wire a tool-using agent for ``task``.

    ``tools`` is a list of plain callables (or ADK ``FunctionTool``s) the agent
    may call; ADK auto-derives their schemas. ``instructions`` appends
    task-specific guidance (e.g. how to run the tests, what "done" means).
    """
    agent = LlmAgent(
        name="Agent",
        instruction=AGENTIC_SYSTEM_PROMPT.format(instructions=instructions).strip(),
        model=model_config or get_model_config("GENERATOR"),
        tools=tools,
    )
    return AgenticEngine(task, agent)
