# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-agent system that implements Tree of Thoughts (ToT) methodology using Google's ADK framework. The system consists of:

- **ToT_Coordinator** (Custom Agent): Orchestrates the workflow using beam search to explore solution spaces
- **Specialist Agents**: Planner, Researcher, Analyzer, Critic, Synthesizer - each handling specific sub-tasks
- **Thought Validator Tool**: Ensures structural integrity of thought nodes

## Core Architecture

- **Entry Point**: `src/mas_tree_of_thought/agent.py` - Creates root_agent instance
- **Coordinator Logic**: `src/mas_tree_of_thought/coordinator.py` - Contains ToTCoordinator class with tree management and beam search
- **Agent Definitions**: `src/mas_tree_of_thought/specialist_agents.py` - Defines all specialist agents
- **Data Models**: `src/mas_tree_of_thought/models.py` - Pydantic models for thought nodes and tree structure
- **LLM Configuration**: `src/mas_tree_of_thought/llm_config.py` - Model configurations for each agent
- **Validation**: `src/mas_tree_of_thought/validation.py` - Thought node validation logic

## Environment Setup

The project requires environment variables in `multi_tool_agent/.env`:

- **Model configs**: `*_MODEL_CONFIG` for each agent (e.g., `PLANNER_MODEL_CONFIG=google:gemini-2.0-flash`)
- **API Keys**: `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY` as needed
- **Optional**: `USE_FREE_TIER_RATE_LIMITING=true` for Google AI Studio free tier

## Common Commands

**Install dependencies:**
```bash
uv sync
```

**Run tests:**
```bash
pytest
```

**Run specific test:**
```bash
pytest tests/test_models.py
```

**Run with coverage:**
```bash
pytest --cov=src/mas_tree_of_thought
```

**Start the agent:**
```bash
adk web
```

## Key Workflow

1. **Initialization**: Root problem → Initial strategies via Planner
2. **Main Loop**: Generate thoughts → Research/Analyze/Critique → Select best k nodes
3. **Synthesis**: Generate final result from high-scoring nodes

The coordinator manages beam search with active_beam tracking the k most promising nodes at each level.