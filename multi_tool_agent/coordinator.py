import asyncio
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from google.adk.agents import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool, ToolContext
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.base_tool import BaseTool
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types
from pydantic import Field
from typing_extensions import override

logger = logging.getLogger(__name__)


class ToTToolset(BaseToolset):
    """Toolset wrapping the thought-node validator tool."""

    def __init__(self, validator: FunctionTool) -> None:
        super().__init__()
        self._validator = validator

    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> list[BaseTool]:
        return [self._validator]

    async def close(self) -> None:
        pass

    @property
    def validator(self) -> FunctionTool:
        return self._validator


class ToTCoordinator(BaseAgent):
    """
    Tree of Thoughts (ToT) Coordinator with Beam Search Implementation.

    Workflow Phases:
    1. Initialization: Create root node and generate initial strategies
    2. Main Loop: Generate candidate thoughts, evaluate, select best nodes
    3. Synthesis: Generate final result from best path
    """

    planner: LlmAgent
    researcher: LlmAgent
    analyzer: LlmAgent
    critic: LlmAgent
    synthesizer: LlmAgent
    toolset: Any  # ToTToolset — Any to satisfy Pydantic arbitrary_types

    model: LlmAgent | LiteLlm | str

    use_free_tier_rate_limiting: bool = Field(default=False)
    free_tier_sleep_seconds: float = Field(default=2.0)
    use_vertex_ai: bool = Field(default=False)

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        planner: LlmAgent,
        researcher: LlmAgent,
        analyzer: LlmAgent,
        critic: LlmAgent,
        synthesizer: LlmAgent,
        validator: FunctionTool,
        model: LlmAgent | LiteLlm | str = None,
    ):
        use_free_tier = os.environ.get("USE_FREE_TIER_RATE_LIMITING", "false").lower() == "true"
        try:
            sleep_secs = float(os.environ.get("FREE_TIER_SLEEP_SECONDS", "2.0"))
        except ValueError:
            logger.warning("Invalid FREE_TIER_SLEEP_SECONDS. Using default: 2.0")
            sleep_secs = 2.0
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"

        toolset = ToTToolset(validator)

        super().__init__(
            name=name,
            description="Tree of Thoughts Coordinator with LLM-driven exploration",
            model=model,
            planner=planner,
            researcher=researcher,
            analyzer=analyzer,
            critic=critic,
            synthesizer=synthesizer,
            toolset=toolset,
            use_free_tier_rate_limiting=use_free_tier,
            free_tier_sleep_seconds=sleep_secs,
            use_vertex_ai=use_vertex,
            sub_agents=[planner, researcher, analyzer, critic, synthesizer],
        )
        logger.info(f"[{self.name}] ToT Coordinator initialized for LLM-driven exploration.")

    # --- State helpers (read via ctx.session.state, write via EventActions delta) ---

    def _get_state_value(self, ctx: InvocationContext, key: str, default: Any = None) -> Any:
        return ctx.session.state.get(key, default)

    def _set_state_value(self, ctx: InvocationContext, key: str, value: Any) -> None:
        """Write a state value and record it in an EventActions delta."""
        ctx.session.state[key] = value

    def _emit_state_event(self, ctx: InvocationContext, delta: Dict[str, Any]) -> Event:
        """Return an Event that carries a state_delta so the SessionService persists it."""
        actions = EventActions(state_delta=delta)
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=actions,
        )

    def _get_thought_tree(self, ctx: InvocationContext) -> Dict[str, Any]:
        return ctx.session.state.setdefault("thought_tree", {})

    def _get_active_beam(self, ctx: InvocationContext) -> List[str]:
        return ctx.session.state.setdefault("active_beam", [])

    def _set_active_beam(self, ctx: InvocationContext, beam: List[str]) -> None:
        ctx.session.state["active_beam"] = beam

    def _update_node(self, ctx: InvocationContext, node_id: str, data: Dict[str, Any]) -> None:
        tree = self._get_thought_tree(ctx)
        if node_id in tree:
            tree[node_id].update(data)
        else:
            tree[node_id] = data

    # --- Score / termination extraction ---

    def _extract_score(self, text: str) -> Optional[float]:
        if not isinstance(text, str):
            return None
        match = re.search(r"Evaluation Score:\s*(\d{1,2}(?:\.\d+)?)/10", text)
        if match:
            try:
                score = float(match.group(1))
                return score if 0 <= score <= 10 else None
            except ValueError:
                return None
        return None

    def _extract_termination_recommendation(self, text: str) -> bool:
        if not isinstance(text, str):
            return False
        match = re.search(r"Termination Recommendation:\s*(True|False)", text, re.IGNORECASE)
        return match.group(1).lower() == "true" if match else False

    # --- Sub-agent runner using before_agent_callback pattern ---

    async def _run_sub_agent_safely(
        self,
        agent: LlmAgent,
        ctx: InvocationContext,
        dynamic_instruction: str | None = None,
    ) -> AsyncGenerator[Event, None]:
        """
        Run a sub-agent, injecting a dynamic instruction via before_agent_callback
        instead of mutating ctx.user_content directly.
        """
        if self.use_free_tier_rate_limiting and isinstance(agent.model, str) and not self.use_vertex_ai:
            await asyncio.sleep(self.free_tier_sleep_seconds)

        original_before = agent.before_agent_callback

        if dynamic_instruction:
            instruction_content = types.Content(parts=[types.Part(text=dynamic_instruction)])

            def _inject_instruction(callback_context: CallbackContext) -> None:
                callback_context._invocation_context.user_content = instruction_content

            agent.before_agent_callback = _inject_instruction

        try:
            async for event in agent.run_async(ctx):
                if (
                    event.content
                    and not event.content.parts
                ):
                    continue
                yield event
        except Exception as e:
            logger.error(f"[{self.name}] Error during sub-agent run ({agent.name}): {e}")
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text=f"Error calling agent {agent.name}: {e}")]),
            )
        finally:
            agent.before_agent_callback = original_before

    # --- Validator helper ---

    async def _validate(self, ctx: InvocationContext, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self.toolset.validator.run_async(
            tool_context=ToolContext(ctx), args=args
        )

    # --- Core workflow ---

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] Starting Tree of Thoughts workflow.")

        # Phase 1: Initialization
        async for event in self._initialize_workflow(ctx):
            yield event

        newly_added_ids = self._get_state_value(ctx, "_initialize_workflow_result", [])
        if not newly_added_ids:
            logger.error(f"[{self.name}] Initialization failed.")
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text="Failed to initialize thought tree.")]),
            )
            return

        for node_id in newly_added_ids:
            self._update_node(ctx, node_id, {"status": "active"})
        self._set_active_beam(ctx, newly_added_ids)
        yield self._emit_state_event(ctx, {"active_beam": newly_added_ids})

        # Phase 2: Beam search loop
        iteration_count = 0
        while True:
            iteration_count += 1
            active_beam = self._get_active_beam(ctx)
            if not active_beam:
                break

            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text=f"Generating thoughts (iteration {iteration_count})...")]),
            )
            async for event in self._generate_next_thoughts(ctx):
                yield event

            if not self._get_state_value(ctx, "_generate_next_thoughts_result", []):
                break

            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text=f"Evaluating new thoughts...")]),
            )
            async for event in self._evaluate_thoughts(ctx):
                yield event

            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text="Selecting viable paths...")]),
            )
            new_beam = await self._select_next_beam(ctx)
            self._set_active_beam(ctx, new_beam)
            yield self._emit_state_event(ctx, {"active_beam": new_beam})

        # Phase 3: Synthesis
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(parts=[types.Part(text="Synthesizing final result...")]),
        )
        async for event in self._synthesize_result(ctx):
            yield event

        logger.info(f"[{self.name}] Tree of Thoughts workflow complete.")

    # --- Phase 1: Initialization ---

    async def _initialize_workflow(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] Initializing workflow.")
        self._set_state_value(ctx, "_initialize_workflow_result", [])

        thought_tree = self._get_thought_tree(ctx)
        if thought_tree:
            logger.warning(f"[{self.name}] Tree already exists — skipping initialization.")
            return

        root_id = "root"
        initial_problem = self._get_state_value(ctx, "initial_problem")
        if not initial_problem and ctx.user_content:
            initial_problem = ctx.user_content.parts[0].text if ctx.user_content.parts else "Default initial problem"
        elif not initial_problem:
            initial_problem = "Solve the initial problem."

        logger.info(f"[{self.name}] Root problem: '{initial_problem}'")
        self._set_state_value(ctx, "initial_problem", initial_problem)

        validation_result = await self._validate(ctx, {
            "parentId": None, "thoughtId": root_id,
            "thought": initial_problem, "depth": 0, "status": "active",
        })
        if validation_result.get("validation_status") == "success":
            self._update_node(ctx, root_id, validation_result)
            yield self._emit_state_event(ctx, {"thought_tree": self._get_thought_tree(ctx)})
            yield Event(
                author=self.toolset.validator.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(
                    text=f"Validated Root Node ({root_id}): '{validation_result.get('thoughtContent', 'N/A')[:100]}...'"
                )]),
            )
        else:
            logger.error(f"[{self.name}] Root node validation failed: {validation_result.get('error')}")
            yield Event(
                author=self.toolset.validator.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(
                    text=f"Validation Failed for Root Node: {validation_result.get('error', 'Unknown error')}"
                )]),
            )
            return

        num_strategies = 3
        planner_instruction = (
            f"Generate exactly {num_strategies} distinct high-level strategies ('thoughts') "
            f"to approach: '{initial_problem}'. Output only the {num_strategies} thoughts, one per line. "
            f"No numbering, no introductory text."
        )

        planner_output = ""
        async for event in self._run_sub_agent_safely(self.planner, ctx, dynamic_instruction=planner_instruction):
            yield event
            if event.content and event.content.parts:
                planner_output = event.content.parts[0].text

        initial_strategies = self._parse_strategies(planner_output, num_strategies, initial_problem)

        newly_added_ids = []
        for i, strategy in enumerate(initial_strategies):
            child_id = f"{root_id}-{i}"
            result = await self._validate(ctx, {
                "parentId": root_id, "thoughtId": child_id,
                "thought": strategy, "depth": 1, "status": "generated",
            })
            if result.get("validation_status") == "success":
                self._update_node(ctx, child_id, result)
                newly_added_ids.append(child_id)
                yield Event(
                    author=self.toolset.validator.name,
                    invocation_id=ctx.invocation_id,
                    content=types.Content(parts=[types.Part(
                        text=f"Validated Initial Strategy ({child_id}): '{result.get('thoughtContent', 'N/A')[:100]}...'"
                    )]),
                )
            else:
                logger.warning(f"[{self.name}] Validation failed for strategy {i}: {result.get('error')}")

        self._set_state_value(ctx, "_initialize_workflow_result", newly_added_ids)
        yield self._emit_state_event(ctx, {
            "_initialize_workflow_result": newly_added_ids,
            "thought_tree": self._get_thought_tree(ctx),
        })

    def _parse_strategies(self, text: str, expected: int, fallback_problem: str) -> List[str]:
        matches = re.findall(r"^\s*Strategy\s*\d+:\s*(.*)", text, re.MULTILINE | re.IGNORECASE)
        if matches:
            return [m.strip() for m in matches]
        lines = [p.strip() for p in text.split("\n") if p.strip()]
        strategies = [s for s in lines if len(s.split()) > 2 and not s.startswith(("*", "-"))]
        if strategies:
            return strategies
        return [f"Develop a comprehensive answer for: {fallback_problem}"]

    # --- Phase 2a: Generate next thoughts ---

    async def _generate_next_thoughts(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        active_beam = self._get_active_beam(ctx)
        thought_tree = self._get_thought_tree(ctx)
        self._set_state_value(ctx, "_generate_next_thoughts_result", [])
        newly_generated = []

        for parent_id in active_beam:
            parent_node = thought_tree.get(parent_id)
            if not parent_node or parent_node.get("status") != "active":
                continue

            parent_thought = parent_node.get("thoughtContent", "")
            parent_depth = parent_node.get("depth", 0)
            parent_score = parent_node.get("evaluationScore")

            score_adj = 1 if (parent_score or 0) >= 8.0 else (-1 if (parent_score or 10) < 4.0 else 0)
            num_to_generate = max(1, 2 + score_adj)

            planner_instruction = (
                f"Current thought: '{parent_thought}' (depth {parent_depth}, score {parent_score or 'N/A'}). "
                f"Generate exactly {num_to_generate} distinct next thoughts (intermediate steps). "
                f"Output only the thoughts, one per line. No numbering or extra text."
            )

            planner_output = ""
            async for event in self._run_sub_agent_safely(self.planner, ctx, dynamic_instruction=planner_instruction):
                yield event
                if event.content and event.content.parts:
                    planner_output = event.content.parts[0].text

            child_thoughts = [p.strip() for p in planner_output.split("\n") if p.strip()][:num_to_generate]
            if not child_thoughts:
                continue

            for i, child_thought in enumerate(child_thoughts):
                child_id = f"{parent_id}-gen{i}"
                result = await self._validate(ctx, {
                    "parentId": parent_id, "thoughtId": child_id,
                    "thought": child_thought, "depth": parent_depth + 1, "status": "generated",
                })
                if result.get("validation_status") == "success":
                    self._update_node(ctx, child_id, result)
                    newly_generated.append(child_id)
                    yield Event(
                        author=self.toolset.validator.name,
                        invocation_id=ctx.invocation_id,
                        content=types.Content(parts=[types.Part(
                            text=f"Validated Thought ({child_id}): '{result.get('thoughtContent', 'N/A')[:100]}...'"
                        )]),
                    )

        self._set_state_value(ctx, "_generate_next_thoughts_result", newly_generated)
        yield self._emit_state_event(ctx, {
            "_generate_next_thoughts_result": newly_generated,
            "thought_tree": self._get_thought_tree(ctx),
        })

    # --- Phase 2b: Evaluate thoughts ---

    async def _evaluate_thoughts(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        thought_tree = self._get_thought_tree(ctx)
        nodes_to_evaluate = [
            (nid, data) for nid, data in thought_tree.items()
            if data.get("status") == "generated"
        ]
        self._set_state_value(ctx, "_evaluate_thoughts_result", [])
        evaluated = []

        for node_id, node_data in nodes_to_evaluate:
            node_thought = node_data.get("thoughtContent", "")

            # Research
            research_findings = "No research conducted."
            try:
                research_instruction = (
                    f"Gather relevant information for the following thought using your search tool. "
                    f"Focus on facts, potential issues, or supporting data.\nThought: {node_thought}"
                )
                final_research_text = None
                async for event in self._run_sub_agent_safely(self.researcher, ctx, dynamic_instruction=research_instruction):
                    yield event
                    if event.content and event.content.parts and event.content.parts[0].text:
                        final_research_text = event.content.parts[0].text
                research_findings = final_research_text or "Researcher returned no findings."
            except Exception as e:
                logger.error(f"[{self.name}] Researcher failed for {node_id}: {e}")
                research_findings = f"Research failed: {e}"

            # Analyze
            analyzer_score, analyzer_output = None, ""
            try:
                analyzer_instruction = (
                    f"Analyze soundness and feasibility of this thought given the research.\n\n"
                    f"Thought: {node_thought}\n\nResearch:\n{research_findings}\n\n"
                    f"Output: `Evaluation Score: [0-10]/10` and `Termination Recommendation: [True/False]`."
                )
                final_analyzer_text = None
                async for event in self._run_sub_agent_safely(self.analyzer, ctx, dynamic_instruction=analyzer_instruction):
                    yield event
                    if event.content and event.content.parts and event.content.parts[0].text:
                        final_analyzer_text = event.content.parts[0].text
                analyzer_output = final_analyzer_text or ""
                analyzer_score = self._extract_score(analyzer_output)
            except Exception as e:
                logger.error(f"[{self.name}] Analyzer failed for {node_id}: {e}")

            # Critique
            critic_score, critic_output = None, ""
            try:
                critic_instruction = (
                    f"Critically evaluate this thought for flaws given the research.\n\n"
                    f"Thought: {node_thought}\n\nResearch:\n{research_findings}\n\n"
                    f"Output: `Evaluation Score: [0-10]/10` and `Termination Recommendation: [True/False]`."
                )
                final_critic_text = None
                async for event in self._run_sub_agent_safely(self.critic, ctx, dynamic_instruction=critic_instruction):
                    yield event
                    if event.content and event.content.parts and event.content.parts[0].text:
                        final_critic_text = event.content.parts[0].text
                critic_output = final_critic_text or ""
                critic_score = self._extract_score(critic_output)
            except Exception as e:
                logger.error(f"[{self.name}] Critic failed for {node_id}: {e}")

            scores = [s for s in [analyzer_score, critic_score] if s is not None]
            final_score = sum(scores) / len(scores) if scores else 1.0
            final_term = self._extract_termination_recommendation(analyzer_output) or \
                         self._extract_termination_recommendation(critic_output)

            update_data = {
                "evaluationScore": final_score,
                "status": "evaluated",
                "researchFindings": research_findings,
                "analyzerOutput": analyzer_output,
                "criticOutput": critic_output,
                "terminationRecommended": final_term,
            }
            self._update_node(ctx, node_id, update_data)
            evaluated.append({**node_data, **update_data})

        self._set_state_value(ctx, "_evaluate_thoughts_result", evaluated)
        yield self._emit_state_event(ctx, {"thought_tree": self._get_thought_tree(ctx)})

    # --- Phase 2c: Select next beam ---

    async def _select_next_beam(self, ctx: InvocationContext) -> List[str]:
        thought_tree = self._get_thought_tree(ctx)
        nodes = [d for d in thought_tree.values() if d.get("status") == "evaluated"]
        if not nodes:
            return []

        nodes.sort(key=lambda x: x.get("evaluationScore", 0.0), reverse=True)
        final_beam = []
        for node_data in nodes:
            node_id = node_data["validatedThoughtId"]
            if node_data.get("terminationRecommended"):
                self._update_node(ctx, node_id, {"status": "terminated_early"})
            else:
                self._update_node(ctx, node_id, {"status": "active"})
                final_beam.append(node_id)

        return final_beam

    # --- Phase 3: Synthesis ---

    async def _synthesize_result(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        thought_tree = self._get_thought_tree(ctx)
        default_error = {"error": "Synthesis could not find a suitable result.", "output": ""}
        self._set_state_value(ctx, "_synthesize_result_result", default_error)

        score_threshold = 7.0
        candidates = [
            d for d in thought_tree.values()
            if d.get("status") in ("evaluated", "active", "terminated_early")
            and d.get("evaluationScore") is not None
        ]

        if not candidates:
            selected = [thought_tree["root"]] if "root" in thought_tree else []
        else:
            candidates.sort(key=lambda x: x.get("evaluationScore", 0.0), reverse=True)
            selected = [n for n in candidates if n.get("evaluationScore", 0.0) >= score_threshold]
            if not selected:
                selected = candidates[:3]

        if not selected:
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text="Synthesis failed: no promising thoughts found.")]),
            )
            return

        initial_problem = self._get_state_value(ctx, "initial_problem", "Unknown problem")
        context_lines = [f"Initial Problem: '{initial_problem}'\n", "High-Scoring Thoughts:"]
        for node in selected:
            context_lines.append(
                f"- ID: {node.get('validatedThoughtId', 'N/A')}, "
                f"Score: {node.get('evaluationScore', 'N/A'):.2f}, "
                f"Thought: {node.get('thoughtContent', 'N/A')}"
            )
        synthesis_context = "\n".join(context_lines)

        synthesis_instruction = (
            f"Synthesize the final answer for the initial problem based on these promising thoughts:\n\n"
            f"{synthesis_context}\n\n"
            f"Integrate the insights to provide a comprehensive, coherent final result."
        )

        final_synthesizer_text = None
        try:
            async for event in self._run_sub_agent_safely(self.synthesizer, ctx, dynamic_instruction=synthesis_instruction):
                yield event
                if (
                    event.author == self.synthesizer.name
                    and event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    final_synthesizer_text = event.content.parts[0].text

            synthesizer_output = final_synthesizer_text or "[Synthesizer returned empty output]"
            self._set_state_value(ctx, "_synthesize_result_result", {"output": synthesizer_output})

            # Save final answer as an artifact if artifact_service is available
            if ctx.artifact_service is not None:
                tool_ctx = ToolContext(ctx)
                await tool_ctx.save_artifact(
                    filename="synthesis_result.txt",
                    artifact=types.Part(text=synthesizer_output),
                )
                logger.info(f"[{self.name}] Synthesis result saved as artifact.")

            yield self._emit_state_event(ctx, {"_synthesize_result_result": {"output": synthesizer_output}})

        except Exception as e:
            logger.error(f"[{self.name}] Synthesizer failed: {e}")
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(parts=[types.Part(text=f"Synthesis failed: {e}")]),
            )
            self._set_state_value(ctx, "_synthesize_result_result", {"error": str(e), "output": ""})
