"""
Dialectica — a reasoning-engine toolbox, kept honest by controlled evals (see README).

The evals collapsed the public surface to what the data actually justifies:

- ``Workflow`` / ``agent`` / ``parallel`` / ``pipeline`` / ``workflow`` (in
  ``dialectica.workflow``) / ``phase`` / ``log`` / ``budget`` / ``args`` /
  ``run_id`` — the composable execution kernel with resume/journal, registry,
  and worktree isolation. ``agent(tools=...)``
  is the one lever that lets a stage genuinely act (read a file, run a
  command, query a service) instead of only rearranging text — the same
  capability a tool-using loop needs, now a first-class primitive instead of
  a dedicated engine class.
- ``create_repair_engine`` — verifier-in-the-loop for verifiable tasks. Ties
  matched-cost best-of-K on pass-rate but reaches it far cheaper
  (short-circuits on success). Verifier is an injected
  ``Callable[[answer], (passed, feedback)]``. Historical cost observations
  depend on the tested task, model and verifier.

Research variants live in ``examples/patterns/`` (not shipped, like ``evals/``).
Historical self-contained experiments did not justify promoting ToT/GAN or
scorer-based ensembles. Open-ended experiments found conditional gains for
heterogeneous reflection and a tuned dialectic; their small task pools and
judge protocols limit generalization. The repeated held-out claim/controller
studies likewise did not establish an adoption-worthy advantage. Reference
patterns compose on the kernel and retain their measured costs and limitations;
execution alone is not evidence of quality. See README Evaluation.

Example:
    from dialectica import Workflow, agent

    async def script():
        return await agent("Your task", tools=[read_file, run_tests])

    result = await Workflow(script).run()

Configuration is read from ``os.environ`` — as a library, Dialectica does NOT
load ``.env`` itself; the consuming application owns environment setup.
"""

from .agent_runtime import TokenUsage
from .repair import IterativeRepairEngine, create_repair_engine
from .workflow import (
    Budget,
    BudgetExhausted,
    Workflow,
    agent,
    args,
    budget,
    in_workflow,
    log,
    parallel,
    phase,
    pipeline,
)

__all__ = [  # noqa: RUF022 — logical grouping, not alphabetical
    # Workflow primitives — the composable execution kernel. agent(tools=...)
    # is what lets a stage add capability instead of only rearranging text.
    "Budget",
    "BudgetExhausted",
    "TokenUsage",
    "Workflow",
    "agent",
    "args",
    "budget",
    "in_workflow",
    "log",
    "parallel",
    "phase",
    "pipeline",
    # Execution-guided repair — verifier-in-the-loop; cost-efficient reliability
    "IterativeRepairEngine",
    "create_repair_engine",
]

__version__ = "0.7.0"
