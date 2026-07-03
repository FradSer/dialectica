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
  ``Callable[[answer], (passed, feedback)]``. The one other proven win
  besides the kernel's tool-using capability.

Everything else this project measured — the agentic engine as its own class,
the heterogeneous ensemble, the dialectic spiral, the legacy ToT+GAN beam
search — either needs nothing beyond ``agent(tools=...)`` or was measured to
tie/lose a prompt-matched single call as a pure-LLM scaffold (dialectic:
0-3-2; ToT+GAN: dominated; ensemble: CUT per the honesty gate — the roster's
robustness gain is heterogeneity, not the scorer's signal). They are kept as
runnable reference patterns in ``examples/patterns/`` (not shipped in the
wheel, same as ``evals/``) — see README "Patterns (not shipped, for
reference)" for the exact verdicts and how to reproduce them.

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

__all__ = [
    # Workflow primitives — the composable execution kernel. agent(tools=...)
    # is what lets a stage add capability instead of only rearranging text.
    "Workflow",
    "Budget",
    "BudgetExhausted",
    "TokenUsage",
    "agent",
    "parallel",
    "pipeline",
    "phase",
    "log",
    "budget",
    "args",
    "in_workflow",
    # Execution-guided repair — verifier-in-the-loop; cost-efficient reliability
    "create_repair_engine",
    "IterativeRepairEngine",
]

__version__ = "0.7.0"
