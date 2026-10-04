"""Unit tests for the role-template agent factory (no network)."""

from pydantic import BaseModel

from dialectica.agent_factory import ROLE_TEMPLATES, create_agent


class _Schema(BaseModel):
    x: int


def test_known_roles_have_templates():
    assert set(ROLE_TEMPLATES) == {"Generator"}


def test_create_agent_uses_role_template_and_name():
    agent = create_agent(role="Generator", role_name="Solver")
    assert agent.name == "Solver"
    assert "Solver" in agent.instruction


def test_unknown_role_falls_back_to_generator():
    agent = create_agent(role="Nonexistent", role_name="X")
    assert "problem-solving assistant" in agent.instruction


def test_output_schema_preserves_tools_for_adk_capability_handling():
    """Given a schema and a tool, creating the agent preserves both for ADK."""

    def lookup() -> int:
        return 1

    agent = create_agent(
        role="Generator",
        role_name="Generator",
        tools=[lookup],
        output_schema=_Schema,
    )
    assert agent.output_schema is _Schema
    assert agent.tools == [lookup]


def test_additional_context_is_injected():
    agent = create_agent(
        role="Generator", role_name="Generator", additional_context="EXTRA RULES"
    )
    assert "EXTRA RULES" in agent.instruction


def test_general_solver_does_not_force_tree_search_on_exact_answer_tasks():
    """Given an exact-answer task, the common role preserves its format contract."""
    agent = create_agent(
        role="Generator",
        role_name="Solver",
        model_config="gemini-test",
        additional_context='Return only {"state": [1, 2]}.',
    )
    assert "thought branches" not in agent.instruction
    assert "output format" in agent.instruction
    assert agent.instruction.endswith('Return only {"state": [1, 2]}.')
