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
    assert "generating high-quality thoughts" in agent.instruction


def test_output_schema_forces_structured_output_and_drops_tools():
    agent = create_agent(
        role="Generator",
        role_name="Generator",
        tools=[lambda: None],
        output_schema=_Schema,
    )
    assert agent.output_schema is _Schema
    assert agent.tools == []


def test_additional_context_is_injected():
    agent = create_agent(
        role="Generator", role_name="Generator", additional_context="EXTRA RULES"
    )
    assert "EXTRA RULES" in agent.instruction
