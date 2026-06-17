"""Step definitions for features/agentic.feature.

The agentic engine's real behavior is the ADK tool-call loop (validated live in
evals/agentic_eval.py); here we mock the single LLM seam and verify the engine's
contract: it wires the injected tools and an act-don't-guess persona into the
agent, and returns the agent's final answer.
"""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, scenarios, then, when

from dialectica import create_agentic_engine

scenarios("features/agentic.feature")


def probe(x: int) -> int:
    """Probe tool: return the hidden value for x."""
    return x


@given("an agentic engine for a task with a probe tool", target_fixture="engine")
def engine():
    return create_agentic_engine("complete the task", tools=[probe])


@when("the agent completes the task", target_fixture="result")
def run_engine(engine):
    async def fake(agent, instruction):
        return "FINAL ANSWER"

    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(engine.run())


@then("it returns the agent's final answer")
def returns_answer(result):
    assert result["final_answer"] == "FINAL ANSWER"


@then("the agent was given the probe tool")
def has_tool(engine):
    assert len(engine.agent.tools) == 1


@then("the agent is instructed to use tools rather than guess")
def persona(engine):
    assert "USING TOOLS" in engine.agent.instruction
