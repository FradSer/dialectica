"""Heterogeneous ensemble search engine — AB-MCTS-lite adaptive search over a roster.

The ensemble is a *capability-adding* engine, not a pure-LLM scaffold.  Like
``repair.py``, it closes the loop a single forward pass cannot:

  - ``repair``: verifier-in-the-loop, **boolean** gate (pass/fail + feedback).
  - ``ensemble``: scorer-in-the-loop, **float** rank (higher = better). The
    scorer is mandatory and positional; constructing without it raises
    ``TypeError``. A caller with only a boolean verifier wraps it:
    ``lambda a: 1.0 if v(a)[0] else 0.0``.

Adaptive wider/deeper branching (AB-MCTS-lite, Sakana arXiv 2503.04412): each
step the engine chooses via Thompson sampling between generating a fresh
candidate ("wider") or refining the current best ("deeper"), and independently
samples which roster arm to call next. All LLM calls route through the single
seam ``agent_runtime.run_agent`` — the only mock point in tests.
"""

import logging
import random
import re
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from google.adk.agents import LlmAgent

from . import agent_runtime
from .agent_factory import create_agent
from .llm_config import _parse_model_config, get_model_config

logger = logging.getLogger(__name__)

Scorer = Callable[[str], float]

SOLVE_PROMPT = """Solve the following problem. Reason it through, then provide your COMPLETE solution.{format_hint}

{problem}"""

WIDEN_PROMPT = """Solve the following problem. A previous approach scored {score:.2f} — produce a GENUINELY DIFFERENT approach, not a minor variation.

Previous (wrong) answer:
{prev_answer}

Problem:
{problem}{format_hint}"""

REFINE_PROMPT = """Refine the following solution. Identify what can be improved and provide a COMPLETE improved solution.{format_hint}

Problem:
{problem}

Current best solution (score {score:.2f}):
{answer}"""


@dataclass
class _ActionArm:
    """Internal action-selection bandit arm (wider vs deeper)."""

    alpha: float = 1.0
    beta: float = 1.0


@dataclass
class ModelArm:
    """One roster member: a baked LlmAgent + its Thompson Beta priors."""

    config: str
    agent: LlmAgent
    name: str
    alpha: float = 1.0
    beta: float = 1.0


@dataclass
class Candidate:
    """A scored answer produced by one ``run_agent`` call."""

    answer: str
    score: float
    model: str  # producing arm's config
    action: str  # "wider" | "deeper"
    depth: int
    parent: int | None = field(default=None)  # index into candidates list


class Policy(Protocol):
    """Injectable strategy for action/arm selection.

    The default implementation is ``ThompsonPolicy`` (Beta-Bernoulli bandit).
    Tests inject a scripted policy for deterministic assertion.
    ``choose_arm`` is only invoked for "wider" moves; the engine uses the
    best-producing arm directly for "deeper" moves.
    """

    def choose_action(
        self, wider: _ActionArm, deeper: _ActionArm, have_candidates: bool
    ) -> str:
        """Return "wider" or "deeper"."""
        ...

    def choose_arm(self, roster: list[ModelArm]) -> ModelArm:
        """Select a model arm from the roster."""
        ...


class ThompsonPolicy:
    """Default Beta-Bernoulli bandit: Thompson-sample action and arm."""

    def __init__(
        self,
        seed: int | None = None,
        rng: random.Random | None = None,
    ):
        self._rng = rng if rng is not None else random.Random(seed)

    def choose_action(
        self, wider: _ActionArm, deeper: _ActionArm, have_candidates: bool
    ) -> str:
        if not have_candidates:
            return "wider"
        w = self._rng.betavariate(wider.alpha, wider.beta)
        d = self._rng.betavariate(deeper.alpha, deeper.beta)
        return "wider" if w >= d else "deeper"

    def choose_arm(self, roster: list[ModelArm]) -> ModelArm:
        draws = [self._rng.betavariate(arm.alpha, arm.beta) for arm in roster]
        return roster[draws.index(max(draws))]


def _safe_agent_name(cfg: str, idx: int) -> str:
    """Convert a roster config string to a valid Python-identifier agent name.

    LlmAgent requires names to be valid Python identifiers (no brackets, colons,
    hyphens, or dots).  The index disambiguates duplicate base names.
    """
    base = cfg.split(":")[-1] if ":" in cfg else cfg
    safe = re.sub(r"[^a-zA-Z0-9]", "_", base)
    if not safe or not safe[0].isalpha():
        safe = "m_" + safe
    return f"Candidate_{safe}" if idx == 0 else f"Candidate_{safe}_{idx}"


class EnsembleSearchEngine:
    """AB-MCTS-lite adaptive search over a heterogeneous roster.

    Each step chooses via the injectable ``policy`` between a "wider" move
    (fresh candidate, optionally cross-model-hinted) and a "deeper" move
    (refine the current best with the arm that produced it). The scorer ranks
    answers; the first answer to reach ``solved_score`` short-circuits the
    budget.
    """

    def __init__(
        self,
        problem: str,
        scorer: Scorer,
        roster: list[ModelArm],
        max_calls: int = 8,
        solved_score: float = 1.0,
        solution_format: str = "",
        policy: Policy | None = None,
    ):
        if scorer is None:
            raise TypeError(
                "scorer is required: EnsembleSearchEngine needs a float-valued "
                "scorer to rank candidates. Wrap a boolean verifier with "
                "'lambda a: 1.0 if v(a)[0] else 0.0'."
            )
        self.problem = problem
        self.scorer = scorer
        self.roster = list(roster)
        self.max_calls = max(1, max_calls)
        self.solved_score = solved_score
        self._format_hint = f" {solution_format}" if solution_format else ""
        self.policy: Policy = policy if policy is not None else ThompsonPolicy()
        self._wider_arm = _ActionArm()
        self._deeper_arm = _ActionArm()

    def _find_arm(self, config: str) -> ModelArm | None:
        for arm in self.roster:
            if arm.config == config:
                return arm
        return None

    async def run(self) -> dict[str, Any]:
        """Execute the AB-MCTS-lite loop; return the best candidate found.

        Return shape (mirrors ``repair.IterativeRepairEngine.run``):
        ``{final_answer, passed, attempts, history, best_score}``.
        ``history`` entries: ``{call, action, model, score, failed}``.
        """
        candidates: list[Candidate] = []
        best: Candidate | None = None
        best_idx: int | None = None
        calls = 0
        history: list[dict[str, Any]] = []

        while calls < self.max_calls:
            if best is not None and best.score >= self.solved_score:
                break

            have = bool(candidates)
            action = self.policy.choose_action(self._wider_arm, self._deeper_arm, have)

            if action == "deeper" and not have:
                action = "wider"

            if action == "deeper" and best is not None:
                arm = self._find_arm(best.model) or self.policy.choose_arm(self.roster)
                prompt = REFINE_PROMPT.format(
                    problem=self.problem,
                    score=best.score,
                    answer=best.answer[:1500],
                    format_hint=self._format_hint,
                )
            else:
                action = "wider"
                arm = self.policy.choose_arm(self.roster)
                if best is not None and best.score < self.solved_score:
                    prompt = WIDEN_PROMPT.format(
                        score=best.score,
                        prev_answer=best.answer[:1500],
                        problem=self.problem,
                        format_hint=self._format_hint,
                    )
                else:
                    prompt = SOLVE_PROMPT.format(
                        problem=self.problem,
                        format_hint=self._format_hint,
                    )

            failed = False
            try:
                answer = (await agent_runtime.run_agent(arm.agent, prompt)).strip()
            except Exception:
                logger.warning(
                    "run_agent raised for arm '%s'; recording as failed candidate",
                    arm.name,
                )
                answer = ""
                failed = True
            # Score outside the guard: a model that raises is a tolerated failed
            # candidate, but a bug in the injected scorer is the caller's and must
            # surface, not be silently swallowed as score 0.0. The scorer may be
            # sync (float) or async (returns an awaitable) — an LLM-judge scorer
            # needs to call run_agent, so await it when required.
            if failed:
                score = 0.0
            else:
                raw = self.scorer(answer)
                score = (await raw) if isinstance(raw, Awaitable) else raw

            calls += 1
            depth = 0 if action == "wider" else (best.depth + 1 if best else 0)
            candidate = Candidate(
                answer=answer,
                score=score,
                model=arm.config,
                action=action,
                depth=depth,
                parent=best_idx,
            )
            candidates.append(candidate)

            reward = 1.0 if best is None else max(0.0, min(1.0, score - best.score))

            if action == "wider":
                self._wider_arm.alpha += reward
                self._wider_arm.beta += 1.0 - reward
            else:
                self._deeper_arm.alpha += reward
                self._deeper_arm.beta += 1.0 - reward

            arm.alpha += reward
            arm.beta += 1.0 - reward

            if best is None or score > best.score:
                best = candidate
                best_idx = len(candidates) - 1

            history.append(
                {
                    "call": calls,
                    "action": action,
                    "model": arm.config,
                    "score": score,
                    "failed": failed,
                }
            )

        if best is None:
            return {
                "final_answer": "",
                "passed": False,
                "attempts": calls,
                "history": history,
                "best_score": 0.0,
            }

        return {
            "final_answer": best.answer,
            "passed": best.score >= self.solved_score,
            "attempts": calls,
            "history": history,
            "best_score": best.score,
        }


def create_ensemble_engine(
    problem: str,
    scorer: Scorer,
    models: list[str] | None = None,
    max_calls: int = 8,
    solved_score: float = 1.0,
    solution_format: str = "",
    policy: Policy | None = None,
) -> EnsembleSearchEngine:
    """Wire an EnsembleSearchEngine with a roster of heterogeneous model arms.

    ``scorer(answer) -> float`` is the mandatory ground-truth ranker; it is
    structurally analogous to ``repair.Verifier`` but returns a float (rank)
    rather than a bool (pass/fail). ``models`` is a list of ``provider:model``
    config strings (e.g. ``["google:gemini-3.5-flash",
    "openrouter:qwen3.6-32b"]``); ``None`` degenerates to a single-model
    best-of-K loop on the default generator config.

    FR6: warns when two roster members resolve to the same effective model
    (e.g. duplicate configs whose provider key is unset fall back to the same
    default — the silent-collapse trap in ``llm_config._parse_model_config``).
    """
    if models is None:
        default = get_model_config("GENERATOR")
        models = [str(default) if not isinstance(default, str) else default]

    # Resolve each 'provider:model' config to the ADK model (bare name or LiteLlm)
    # ONCE: create_agent does not parse, so the roster must hand it a resolved
    # model — otherwise an 'openrouter:'/'openai:' arm is passed as a bare string,
    # never wrapped in LiteLlm, and silently never routes to that provider.
    resolved = [_parse_model_config(cfg) for cfg in models]

    # FR6: warn when heterogeneity is lost — duplicate effective models, or a
    # non-google arm that silently fell back to the default (its provider key is
    # unset, so _parse_model_config returns the bare default string).
    effective_keys = [
        r if isinstance(r, str) else getattr(r, "model", str(r)) for r in resolved
    ]
    duplicates = {k for k in effective_keys if effective_keys.count(k) > 1}
    fallbacks = [
        cfg
        for cfg, r in zip(models, resolved)
        if isinstance(r, str)
        and cfg.split(":", 1)[0].lower() in ("openrouter", "openai")
    ]
    if duplicates:
        warnings.warn(
            f"Ensemble roster collapsed to duplicate effective model(s): "
            f"{duplicates}. Heterogeneous diversity is lost; use distinct "
            "provider:model configs.",
            UserWarning,
            stacklevel=2,
        )
    if fallbacks:
        warnings.warn(
            f"Ensemble roster member(s) {fallbacks} silently fell back to the "
            "default model (provider key unset). Set the provider's API key or "
            "remove the member; the intended model is not being used.",
            UserWarning,
            stacklevel=2,
        )

    name_counts: dict[str, int] = {}
    roster: list[ModelArm] = []
    for cfg, model in zip(models, resolved):
        base = cfg.split(":")[-1] if ":" in cfg else cfg
        idx = name_counts.get(base, 0)
        name_counts[base] = idx + 1
        arm_name = _safe_agent_name(cfg, idx)
        agent = create_agent(role="Generator", role_name=arm_name, model_config=model)
        roster.append(ModelArm(config=cfg, agent=agent, name=arm_name))

    return EnsembleSearchEngine(
        problem=problem,
        scorer=scorer,
        roster=roster,
        max_calls=max_calls,
        solved_score=solved_score,
        solution_format=solution_format,
        policy=policy,
    )
