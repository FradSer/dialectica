"""Dynamic agent factory for creating specialist agents at runtime.

Creates LlmAgent instances from role templates. Generator is the only
surviving role: the Discriminator/Synthesizer templates were specific to the
ToT+GAN engine and dialectic engine, both demoted to reference patterns
(``examples/patterns/``) — those scripts call ``wf.agent(prompt,
instructions=<bespoke framing text>)`` instead of a dedicated role template.
"""

import logging
from typing import Any

from google.adk.agents import LlmAgent

from .llm_config import get_model_config

logger = logging.getLogger(__name__)


# Agent role templates - used to generate instructions for common roles.
# ``{additional_context}`` is deliberately LAST, not sandwiched in the middle:
# a caller injecting task-specific framing via ``wf.agent(instructions=...)``
# (e.g. the agentic pattern's "act, don't guess — use tools" charter) needs
# that framing to have the final word, not be followed by this template's own
# generic "generate thought branches" closing line, which would otherwise
# directly contradict it.
ROLE_TEMPLATES = {
    "Generator": {
        "system_prompt": """You are a {role_name} responsible for generating high-quality thoughts.

Your task:
- Generate creative, diverse, and well-reasoned thought branches
- Each thought should be distinct and explore different angles
- Build on the parent context when provided
- Be specific and actionable, not vague or generic
- Generate thoughts that advance the problem-solving process

{additional_context}""",
        "tools": [],
    },
}

# Named subagent types mirroring Claude Code Workflow's agent_type option.
AGENT_TYPE_PRESETS: dict[str, str] = {
    "Explore": """You are in read-only exploration mode.
- Search, read, and map the codebase or data — do not edit files or run mutating commands.
- Report findings concretely: paths, symbols, and evidence.
- Stop when you have enough context to answer the task; do not speculate beyond what you observed.""",
}


def create_agent(
    role: str,
    role_name: str | None = None,
    additional_context: str = "",
    tools: list[Any] | None = None,
    model_config: str | None = None,
    output_schema: type | None = None,
    agent_type: str | None = None,
) -> LlmAgent:
    """Create a specialist agent with a specific role.

    Args:
        role: The agent role (Generator, Discriminator, Synthesizer)
        role_name: Optional custom name for the role (defaults to role)
        additional_context: Extra context to inject into the system prompt
        tools: Optional list of tools to give the agent
        model_config: Optional model config string (defaults to role-based config)
        output_schema: Optional Pydantic model forcing structured JSON output.
            ADK disallows combining ``output_schema`` with tools, so tools are
            dropped when a schema is supplied.

    Returns:
        LlmAgent configured for the specified role
    """
    if role not in ROLE_TEMPLATES:
        logger.warning("Unknown role '%s', using Generator template", role)
        role = "Generator"

    template = ROLE_TEMPLATES[role]
    effective_role_name = role_name or role

    type_context = ""
    if agent_type:
        preset = AGENT_TYPE_PRESETS.get(agent_type)
        if preset is None:
            logger.warning("Unknown agent_type %r, ignoring", agent_type)
        else:
            type_context = preset.strip()

    combined_context = "\n\n".join(
        part for part in (type_context, additional_context.strip()) if part
    )

    # Build the system prompt. Strip trailing whitespace left by an empty
    # additional_context (the common case for plain wf.agent() calls with no
    # instructions=).
    system_prompt = (
        template["system_prompt"]
        .format(
            role_name=effective_role_name,
            additional_context=combined_context,
        )
        .strip()
    )

    # output_schema and tools are mutually exclusive in ADK.
    effective_tools = (
        [] if output_schema else (tools if tools is not None else template["tools"])
    )

    # Get model config (use role-specific override if available)
    effective_model = model_config if model_config else get_model_config(role)

    agent = LlmAgent(
        name=effective_role_name,
        instruction=system_prompt,
        model=effective_model,
        tools=effective_tools,
        output_schema=output_schema,
    )

    logger.info(
        "Created agent '%s' (role=%s, tools=%d, structured=%s)",
        effective_role_name,
        role,
        len(effective_tools),
        output_schema is not None,
    )

    return agent
