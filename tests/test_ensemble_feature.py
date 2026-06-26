"""Step definitions for features/ensemble.feature.

Mocks the LLM seam (agent_runtime.run_agent) and injects scripted scorers and
policies, exercising the real ensemble control flow without touching the network.
"""

import asyncio
import warnings
from typing import Any
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import EnsembleSearchEngine, create_ensemble_engine
from dialectica.ensemble import ModelArm
from tests.helpers import RAISE, make_ensemble_fake

scenarios("features/ensemble.feature")


# ── Scripted policy for deterministic tests ───────────────────────────────────


class ScriptedPolicy:
    """Pre-scripted action sequence + round-robin arm selection.

    ``choose_arm`` is only called for "wider" moves; the engine uses the
    best-producing arm directly for "deeper" moves.
    """

    def __init__(self, moves: list[str]):
        self._moves = list(moves)
        self._arm_index = 0

    def choose_action(self, wider: Any, deeper: Any, have_candidates: bool) -> str:
        return self._moves.pop(0) if self._moves else "wider"

    def choose_arm(self, roster: list[ModelArm]) -> ModelArm:
        arm = roster[self._arm_index % len(roster)]
        self._arm_index += 1
        return arm


# ── Fake agent builder ────────────────────────────────────────────────────────


def _fake_agent(name: str):
    from google.adk.agents import LlmAgent

    # LlmAgent.name must be a valid Python identifier (no brackets).
    return LlmAgent(name=name, instruction="", model="gemini-3.5-flash")


def _arm_name(cfg: str) -> str:
    """Convert a roster config to a valid Python-identifier arm name."""
    return f"Candidate_{cfg}"


def _build_roster(names: list[str]) -> list[ModelArm]:
    return [
        ModelArm(
            config=name,
            agent=_fake_agent(_arm_name(name)),
            name=_arm_name(name),
        )
        for name in names
    ]


# ── Background ────────────────────────────────────────────────────────────────


@given('a roster of three models "alpha", "beta", and "gamma"', target_fixture="ctx")
def background_ctx():
    scores_map: dict[str, float] = {}
    return {
        "roster_names": ["alpha", "beta", "gamma"],
        "model_outputs": {},
        "scorer": lambda ans: scores_map.get(ans, 0.5),
        "_scores_map": scores_map,
        "policy": None,
        "max_calls": 8,
        "solved_score": 1.0,
    }


# ── Given steps ───────────────────────────────────────────────────────────────


@given(
    parsers.re(
        r"each model produces a candidate the scorer rates "
        r"alpha=(?P<a>[\d.]+) beta=(?P<b>[\d.]+) gamma=(?P<g>[\d.]+)"
    )
)
def each_model_scores(ctx, a, b, g):
    ctx["model_outputs"].update(
        {
            "Candidate_alpha": "ans_alpha",
            "Candidate_beta": "ans_beta",
            "Candidate_gamma": "ans_gamma",
        }
    )
    ctx["_scores_map"].update(
        {
            "ans_alpha": float(a),
            "ans_beta": float(b),
            "ans_gamma": float(g),
        }
    )
    ctx["policy"] = ScriptedPolicy(["wider", "wider", "wider"])


@given(parsers.re(r"a max-calls budget of (?P<n>\d+)"))
def set_budget(ctx, n):
    ctx["max_calls"] = int(n)


@given(parsers.re(r'a deterministic policy scripted as "(?P<moves>[^"]+)"'))
def set_scripted_policy(ctx, moves):
    ctx["policy"] = ScriptedPolicy([m.strip() for m in moves.split(",")])


@given("every candidate the scorer can rate")
def scoreable_candidates(ctx):
    ctx["model_outputs"].update(
        {
            "Candidate_alpha": "ans_alpha",
            "Candidate_beta": "ans_beta",
            "Candidate_gamma": "ans_gamma",
        }
    )
    ctx["_scores_map"].update({"ans_alpha": 0.5, "ans_beta": 0.5, "ans_gamma": 0.5})


@given(
    parsers.re(
        r'model "(?P<name>[^"]+)" produces a candidate the scorer rates (?P<score>[\d.]+)$'
    )
)
def model_produces_score(ctx, name, score):
    key = f"ans_{name}_wider"
    ctx["model_outputs"][_arm_name(name)] = key
    ctx["_scores_map"][key] = float(score)


@given(parsers.re(r'going deeper on "(?P<name>[^"]+)" cannot exceed (?P<cap>[\d.]+)'))
def deeper_capped(ctx, name, cap):
    existing = ctx["model_outputs"].get(_arm_name(name), f"ans_{name}_wider")
    wider_key = existing if isinstance(existing, str) else existing[0]
    deeper_key = f"ans_{name}_deeper"
    ctx["model_outputs"][_arm_name(name)] = [wider_key, deeper_key]
    ctx["_scores_map"][deeper_key] = float(cap)


@given(
    parsers.re(
        r'model "(?P<name>[^"]+)" produces a candidate the scorer rates (?P<score>[\d.]+) when sampled wider'
    )
)
def model_produces_wider_score(ctx, name, score):
    key = f"ans_{name}_wider"
    ctx["model_outputs"][_arm_name(name)] = key
    ctx["_scores_map"][key] = float(score)
    ctx["policy"] = ScriptedPolicy(["wider", "deeper", "wider", "wider"])


@given("a roster that would keep producing candidates indefinitely")
def infinite_roster(ctx):
    ctx["model_outputs"].update(
        {
            "Candidate_alpha": "ans_alpha_inf",
            "Candidate_beta": "ans_beta_inf",
            "Candidate_gamma": "ans_gamma_inf",
        }
    )
    ctx["_scores_map"].update(
        {"ans_alpha_inf": 0.0, "ans_beta_inf": 0.0, "ans_gamma_inf": 0.0}
    )
    ctx["policy"] = ScriptedPolicy(["wider"] * 100)


@given(parsers.re(r"the best candidate seen within budget scores (?P<s>[\d.]+)"))
def best_within_budget(ctx, s):
    ctx["model_outputs"]["Candidate_alpha"] = "ans_alpha_best"
    ctx["_scores_map"]["ans_alpha_best"] = float(s)


@given('model "beta" raises when called')
def beta_raises(ctx):
    ctx["model_outputs"]["Candidate_beta"] = RAISE


@given(
    parsers.re(
        r'models "alpha" and "gamma" produce candidates rated (?P<a>[\d.]+) and (?P<g>[\d.]+)'
    )
)
def alpha_gamma_rated(ctx, a, g):
    ctx["model_outputs"]["Candidate_alpha"] = "ans_alpha_rated"
    ctx["model_outputs"]["Candidate_gamma"] = "ans_gamma_rated"
    ctx["_scores_map"]["ans_alpha_rated"] = float(a)
    ctx["_scores_map"]["ans_gamma_rated"] = float(g)
    ctx["policy"] = ScriptedPolicy(["wider", "wider", "wider"])


@given("every model produces a candidate the scorer rates 0.0")
def every_model_zero(ctx):
    ctx["model_outputs"].update(
        {
            "Candidate_alpha": "ans_alpha_zero",
            "Candidate_beta": "ans_beta_zero",
            "Candidate_gamma": "ans_gamma_zero",
        }
    )
    ctx["_scores_map"].update(
        {"ans_alpha_zero": 0.0, "ans_beta_zero": 0.0, "ans_gamma_zero": 0.0}
    )
    ctx["policy"] = ScriptedPolicy(["wider", "wider", "wider"])


# ── When steps ────────────────────────────────────────────────────────────────


@when("the ensemble searches", target_fixture="result")
def run_ensemble(ctx):
    roster = _build_roster(ctx["roster_names"])
    scorer = ctx["scorer"]
    policy = ctx["policy"] or ScriptedPolicy(["wider"] * ctx["max_calls"])
    fake, _counter = make_ensemble_fake(ctx["model_outputs"])
    engine = EnsembleSearchEngine(
        problem="test problem",
        scorer=scorer,
        roster=roster,
        max_calls=ctx["max_calls"],
        solved_score=ctx["solved_score"],
        policy=policy,
    )
    with patch("dialectica.agent_runtime.run_agent", fake):
        return asyncio.run(engine.run())


@when("an ensemble engine is constructed without a scorer", target_fixture="result")
def construct_without_scorer(ctx):
    try:
        EnsembleSearchEngine(problem="test", scorer=None, roster=[])
        return {"error": None}
    except (TypeError, ValueError) as exc:
        return {"error": exc}


# ── Then steps ────────────────────────────────────────────────────────────────


@then(parsers.re(r'the winning answer is the one from model "(?P<name>[^"]+)"'))
def winning_from_model(result, name):
    best_entry = max(result["history"], key=lambda e: e["score"])
    assert best_entry["model"] == name, (
        f"expected best model '{name}', got '{best_entry['model']}'"
    )


@then(parsers.re(r"the winning score is (?P<s>[\d.]+)$"))
def winning_score_exact(result, s):
    best_score = max(e["score"] for e in result["history"])
    assert abs(best_score - float(s)) < 1e-9, f"expected score {s}, got {best_score}"


@then(parsers.re(r'the move sequence taken was "(?P<moves>[^"]+)"'))
def move_sequence(result, moves):
    expected = [m.strip() for m in moves.split(",")]
    actual = [e["action"] for e in result["history"]]
    assert actual == expected, f"expected moves {expected}, got {actual}"


@then("a wider move sampled a not-yet-used model")
def wider_sampled_fresh(result):
    wider_entries = [e for e in result["history"] if e["action"] == "wider"]
    wider_models = [e["model"] for e in wider_entries]
    assert len(wider_models) == len(set(wider_models)), (
        f"wider moves reused a model: {wider_models}"
    )


@then("a deeper move re-prompted the current best model")
def deeper_used_best(result):
    best_model: str | None = None
    best_score = -1.0
    for i, entry in enumerate(result["history"]):
        if entry["action"] == "deeper":
            assert entry["model"] == best_model, (
                f"deeper call #{i + 1} used '{entry['model']}' "
                f"but current best was '{best_model}'"
            )
        if entry["score"] > best_score:
            best_score = entry["score"]
            best_model = entry["model"]


@then(parsers.re(r"the winning score is at least (?P<s>[\d.]+)"))
def winning_score_at_least(result, s):
    best_score = max(e["score"] for e in result["history"])
    assert best_score >= float(s), f"expected score >= {s}, got {best_score}"


@then("construction fails with a missing-scorer error")
def construction_failed(result):
    assert result["error"] is not None, "expected construction to raise but it did not"


@then(parsers.re(r"the engine made exactly (?P<n>\d+) model calls?"))
def exact_model_calls(result, n):
    assert result["attempts"] == int(n), f"expected {n} calls, got {result['attempts']}"


@then(parsers.re(r"the returned answer is the best-so-far scoring (?P<s>[\d.]+)"))
def answer_best_score(result, s):
    assert abs(result["best_score"] - float(s)) < 1e-9, (
        f"expected best_score {s}, got {result['best_score']}"
    )


@then("the result reports passed is false")
def result_not_passed(result):
    assert result["passed"] is False


@then("the result reports passed is true")
def result_passed(result):
    assert result["passed"] is True


@then("the search reports it did not find a satisfactory answer")
def search_not_satisfied(result):
    assert result["passed"] is False


@then("it still returns the best-effort candidate rather than raising")
def returns_best_effort(result):
    assert "final_answer" in result


@then("the search completes without raising")
def search_no_raise(result):
    assert result is not None


@then('the failed model "beta" is recorded as a failed candidate')
def failed_model_recorded(result):
    failed = [e for e in result["history"] if e["failed"] and "beta" in e["model"]]
    assert failed, (
        f"expected a failed entry for 'beta' in history, got: {result['history']}"
    )


# ── FR6 roster-distinctness unit test ─────────────────────────────────────────


def test_fr6_roster_distinctness(monkeypatch):
    """FR6: warn when roster members collapse to the same effective model.

    With OPENROUTER_API_KEY unset, both ``openrouter:*`` entries fall back to
    gemini-3.5-flash — the engine must warn about the silent collapse.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        create_ensemble_engine(
            problem="test",
            scorer=lambda ans: 0.0,
            models=["openrouter:qwen3.6-32b", "openrouter:qwen3.6-32b"],
        )

    assert any(
        issubclass(w.category, UserWarning)
        and (
            "collapsed" in str(w.message).lower()
            or "duplicate" in str(w.message).lower()
        )
        for w in caught
    ), (
        f"expected a UserWarning about roster collapse, got: {[str(w.message) for w in caught]}"
    )


def test_roster_configs_are_parsed_to_resolved_models():
    """C2 regression guard: roster 'provider:model' configs must be resolved
    before create_agent (which does NOT parse). A raw 'google:gemini-3.5-flash'
    would leak the 'google:' prefix into agent.model; parsing yields the bare
    model name. The raw config is still kept for history/attribution.
    """
    engine = create_ensemble_engine(
        problem="p", scorer=lambda a: 1.0, models=["google:gemini-3.5-flash"]
    )
    assert engine.roster[0].agent.model == "gemini-3.5-flash"
    assert engine.roster[0].config == "google:gemini-3.5-flash"
