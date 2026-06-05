"""Tests for list parsing and the default LlmGenerator."""

from unittest.mock import patch

from dialectica.agent_factory import create_agent
from dialectica.generation import LlmGenerator, parse_list
from dialectica.models import ThoughtData


def test_parse_multiline_items_keep_body():
    # Regression: multi-line items used to collapse to their first line only.
    text = (
        "1. **First strategy**\n"
        "   detailed body line A\n"
        "   detailed body line B\n"
        "2. **Second strategy**\n"
        "   another body\n"
    )
    items = parse_list(text)
    assert len(items) == 2
    assert "detailed body line A" in items[0]
    assert "detailed body line B" in items[0]
    assert items[0].startswith("**First strategy**")


def test_parse_paren_and_bullet_markers():
    assert len(parse_list("1) alpha\n2) beta")) == 2
    assert len(parse_list("- alpha\n- beta\n* gamma")) == 3


def test_parse_fallback_plain_lines():
    assert parse_list("alpha\nbeta\ngamma") == ["alpha", "beta", "gamma"]


async def test_generator_uses_strategy_prompt_for_root():
    gen = LlmGenerator(create_agent(role="Generator", role_name="Generator"))
    captured = {}

    async def fake(agent, instruction):
        captured["instruction"] = instruction
        return "1. alpha\n2. beta"

    root = ThoughtData(thoughtId="root", thought="the problem", depth=0)
    with patch("dialectica.agent_runtime.run_agent", fake):
        items = await gen.expand(root, "the problem")

    assert items == ["alpha", "beta"]
    assert "initial strategies" in captured["instruction"].lower()


async def test_generator_caps_item_count():
    # Regression: nested-markdown output once exploded into 21 "strategies".
    gen = LlmGenerator(create_agent(role="Generator", role_name="Generator"), max_items=5)
    many = "\n".join(f"{i}. item {i}" for i in range(1, 21))  # 20 items

    async def fake(agent, instruction):
        return many

    root = ThoughtData(thoughtId="root", thought="p", depth=0)
    with patch("dialectica.agent_runtime.run_agent", fake):
        items = await gen.expand(root, "p")
    assert len(items) == 5


async def test_generator_uses_child_prompt_for_inner_node():
    gen = LlmGenerator(create_agent(role="Generator", role_name="Generator"))
    captured = {}

    async def fake(agent, instruction):
        captured["instruction"] = instruction
        return "1. step one\n2. step two"

    node = ThoughtData(thoughtId="root_s0", parentId="root", thought="a strategy", depth=1)
    with patch("dialectica.agent_runtime.run_agent", fake):
        items = await gen.expand(node, "the problem")

    assert items == ["step one", "step two"]
    assert "next steps" in captured["instruction"].lower()
    assert "a strategy" in captured["instruction"]
