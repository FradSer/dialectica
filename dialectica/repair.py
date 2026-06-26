"""Execution-guided repair — Dialectica's core engine, the one that structurally
beats a single strong-model call.

Controlled evals settled it: pure-LLM reasoning scaffolds (ToT, GAN, the
dialectic) only rearrange the model's own thinking on the same context — they
add no information, so they tie a prompt-matched single call. A scaffold beats
one pass only by doing something one pass cannot: act on objective ground truth
and react. This engine is that loop — generate -> run the verifier -> feed the
CONCRETE failure back -> regenerate — until the verifier passes or attempts run
out.

The verifier is injected as a plain ``Callable[[answer], (passed, feedback)]``,
so the engine is task-agnostic: it works for ANY objective checker — unit tests,
a schema validator, a linter, a SQL ``EXPLAIN``, assertion-checked business
logic — not just code. The consuming app supplies "how to check it"; the edge
over one shot is the ground-truth feedback the single pass never sees (not an
LLM self-score on the same model, which the evals showed adds nothing).

**Relation to the ensemble engine** — repair is *deeper-only*: a single roster
rotates round-robin on each failure, and the verifier returns a boolean pass/fail
with concrete feedback. The ensemble engine (``ensemble.py``) is *wider+deeper*:
it adaptively chooses between sampling a fresh arm and refining the current best,
ranks answers with a mandatory float scorer, and returns the highest-scoring one.
Both need a ground-truth-grade signal a single pass lacks; choose repair when the
signal is a pass/fail verifier, ensemble when it is a real-valued score.
"""

import logging
import re
from collections.abc import Callable
from typing import Any, Optional

from google.adk.agents import LlmAgent

from . import agent_runtime
from .agent_factory import create_agent
from .llm_config import _parse_model_config, get_model_config

logger = logging.getLogger(__name__)

# Given the model's raw answer, return (passed, feedback). ``feedback`` is the
# concrete failure to repair against (assertion errors, wrong output, a stack
# trace) — empty when it passed.
Verifier = Callable[[str], tuple[bool, str]]

SOLVE_PROMPT = """Solve the following problem. Reason it through, then provide your COMPLETE solution.{format_hint}

{problem}"""

REPAIR_PROMPT = """Your solution did NOT pass verification. Below is every previous attempt and the EXACT failure each produced — use the full history so you do not repeat a fix that already failed, and do not restart from scratch unless the whole approach is wrong.

**Problem:**
{problem}

**Previous attempts and their verifier failures (ground truth):**
{history_block}

Diagnose what specifically failed — and, if earlier fixes did not work, why — then provide your COMPLETE corrected solution.{format_hint}"""


def _safe_agent_name(config: str) -> str:
    """Coerce a ``provider:model`` config to a valid ADK agent name.

    ADK requires agent names to be valid Python identifiers, so ``:``/``.``/``-``
    in a model config are replaced. A bare identifier (e.g. a test label ``"A"``)
    is returned unchanged. Used only for the agent name — the raw config is what
    the run trace records as the model that produced each attempt.
    """
    base = config.split(":", 1)[-1] if ":" in config else config
    safe = re.sub(r"[^a-zA-Z0-9]", "_", base)
    if not safe or not safe[0].isalpha():
        safe = "m_" + safe
    return safe


class IterativeRepairEngine:
    """Generate -> verify -> repair-against-the-failure, until pass or out of tries.

    Accepts a single generator agent or a roster of agents. With a roster, each
    failed attempt rotates to the next model round-robin, cycling back when the
    roster is exhausted. A one-element roster is byte-identical to a single agent.
    """

    def __init__(
        self,
        problem: str,
        generator: LlmAgent | list[LlmAgent],
        verifier: Verifier,
        max_attempts: int = 3,
        solution_format: str = "",
        model_labels: list[str] | None = None,
    ):
        self.problem = problem
        # Normalize to a list so the single-agent and roster paths are identical.
        self._generators: list[LlmAgent] = (
            generator if isinstance(generator, list) else [generator]
        )
        # The label recorded in history per attempt. Defaults to the agent name,
        # but callers pass the raw ``provider:model`` config (which ADK forbids as
        # an agent name) so the trace attributes attempts to the real model.
        self._labels: list[str] = model_labels or [g.name for g in self._generators]
        self.verifier = verifier
        self.max_attempts = max(1, max_attempts)
        # Optional domain output-format hint (e.g. "Return a single ```python
        # code block." or "Return only the JSON object."); keeps the engine
        # general while letting callers pin the format their verifier parses.
        self._format_hint = f" {solution_format}" if solution_format else ""

    @staticmethod
    def _history_block(failed: list[tuple[str, str]]) -> str:
        """Render every prior failed attempt + its verifier failure (bounded)."""
        return "\n\n".join(
            f"--- Attempt {i} ---\n{ans[:1500]}\n[Verifier failure]: {fb[:500]}"
            for i, (ans, fb) in enumerate(failed, 1)
        )

    async def run(self) -> dict[str, Any]:
        """Solve with verifier-in-the-loop; return the final answer + trace.

        Each history entry carries ``{"attempt": n, "passed": bool, "model": label}``
        where ``label`` is the roster member (the raw ``provider:model`` config for
        a roster, else the agent name) that produced the attempt.
        """
        idx = 0
        generator = self._generators[idx]
        answer = (
            await agent_runtime.run_agent(
                generator,
                SOLVE_PROMPT.format(
                    problem=self.problem, format_hint=self._format_hint
                ),
            )
        ).strip()
        passed, feedback = self.verifier(answer)
        history: list[dict[str, Any]] = [
            {"attempt": 1, "passed": passed, "model": self._labels[idx]}
        ]
        logger.info("Attempt 1: passed=%s (model=%s)", passed, self._labels[idx])

        failed: list[tuple[str, str]] = []
        attempt = 1
        while not passed and attempt < self.max_attempts:
            failed.append((answer, feedback))
            attempt += 1
            idx = (attempt - 1) % len(self._generators)
            generator = self._generators[idx]
            answer = (
                await agent_runtime.run_agent(
                    generator,
                    REPAIR_PROMPT.format(
                        problem=self.problem,
                        history_block=self._history_block(failed),
                        format_hint=self._format_hint,
                    ),
                )
            ).strip()
            passed, feedback = self.verifier(answer)
            history.append(
                {"attempt": attempt, "passed": passed, "model": self._labels[idx]}
            )
            logger.info(
                "Repair attempt %d: passed=%s (model=%s)",
                attempt,
                passed,
                self._labels[idx],
            )

        return {
            "final_answer": answer,
            "passed": passed,
            "attempts": attempt,
            "history": history,
        }


def create_repair_engine(
    problem: str,
    verifier: Verifier,
    max_attempts: int = 3,
    model_config: Optional[str] = None,
    solution_format: str = "",
    models: list[str] | None = None,
) -> IterativeRepairEngine:
    """Wire an IterativeRepairEngine with one Generator agent or a roster.

    ``verifier(raw_answer) -> (passed, feedback)`` is the objective checker; the
    engine is task-agnostic and only reacts to what it returns. ``solution_format``
    optionally pins the output shape the verifier expects (e.g. a ```python code
    block, or "only the JSON object").

    Pass ``models`` to enable round-robin rotation over a roster of model configs
    (``"provider:model_name"`` strings). Each failed attempt rotates to the next
    model; the cycle wraps back when all members have been tried. This is
    deeper-only rotation with a boolean verifier — see ``ensemble.py`` for
    wider+deeper sampling with a float scorer.

    ``model_config`` and ``models`` are mutually exclusive; passing both raises
    ``ValueError``.
    """
    if model_config is not None and models is not None:
        raise ValueError(
            "conflicting configuration: pass either model_config (single model) "
            "or models (roster), not both"
        )
    if models is not None:
        # ADK forbids ':'/'.'/'-' in agent names, so sanitize the config for the
        # name but keep the raw config as the history label (model attribution).
        name_counts: dict[str, int] = {}
        generators: list[LlmAgent] = []
        for m in models:
            base = _safe_agent_name(m)
            dup = name_counts.get(base, 0)
            name_counts[base] = dup + 1
            arm_name = base if dup == 0 else f"{base}_{dup}"
            # create_agent does not parse: resolve 'provider:model' to the ADK
            # model so non-google arms are wrapped in LiteLlm and actually route.
            generators.append(
                create_agent(
                    role="Generator",
                    role_name=arm_name,
                    model_config=_parse_model_config(m),
                )
            )
        labels: list[str] | None = list(models)
    else:
        generators = [
            create_agent(
                role="Generator",
                role_name="Solver",
                model_config=model_config or get_model_config("GENERATOR"),
            )
        ]
        labels = None
    return IterativeRepairEngine(
        problem, generators, verifier, max_attempts, solution_format, labels
    )
