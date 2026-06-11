"""Dynamic agent factory for creating specialist agents at runtime.

Creates LlmAgent instances from role templates (Generator, Discriminator,
Synthesizer) with per-role prompts, tools, and model configuration.
"""

import logging
from typing import Any

from google.adk.agents import LlmAgent

from .llm_config import get_model_config

logger = logging.getLogger(__name__)


# Agent role templates - used to generate instructions for common roles
ROLE_TEMPLATES = {
    "Generator": {
        "system_prompt": """You are a {role_name} responsible for generating high-quality thoughts.

Your task:
- Generate creative, diverse, and well-reasoned thought branches
- Each thought should be distinct and explore different angles
- Build on the parent context when provided
- Be specific and actionable, not vague or generic

{additional_context}

Generate thoughts that advance the problem-solving process.""",
        "tools": [],
    },
    "Discriminator": {
        "system_prompt": """You are a {role_name} responsible for critically evaluating thoughts.

Your task:
- Evaluate thoughts with rigorous skepticism
- Identify logical flaws, weak assumptions, and potential issues
- Provide specific, actionable feedback for improvement
- Assess feasibility and quality objectively
- Recommend termination only if the path is fundamentally flawed

{additional_context}

Your evaluation will drive iterative refinement, so be thorough and constructive.""",
        "tools": [],
    },
    "Synthesizer": {
        "system_prompt": """You are a {role_name} responsible for integrating insights into a final answer.

Your task:
- Analyze the best-performing thought branches
- Identify common themes and complementary insights
- Synthesize a coherent, comprehensive solution
- Resolve any conflicts between different approaches
- Present the final answer clearly and completely

{additional_context}

Create a unified solution from the strongest reasoning paths.""",
        "tools": [],
    },
}


def create_agent(
    role: str,
    role_name: str | None = None,
    additional_context: str = "",
    tools: list[Any] | None = None,
    model_config: str | None = None,
    output_schema: type | None = None,
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

    # Build the system prompt
    system_prompt = template["system_prompt"].format(
        role_name=effective_role_name,
        additional_context=additional_context,
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
