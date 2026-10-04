"""Deployable final-selection rules over saved self-refinement trajectories."""

import json

import pytest

from evals.research_tasks import make_portfolio_tasks
from evals.selection_rules import (
    checker_index,
    convergence_index,
    plurality_index,
    selector_indices,
)


def answer(*selected: int) -> str:
    return json.dumps({"selected": list(selected)})


def test_plurality_prefers_most_common_prediction_and_latest_on_tie():
    answers = [answer(1, 2), answer(3), answer(1, 2), answer(3)]
    assert plurality_index(answers, "portfolio") == 3  # tie -> latest occurrence
    assert plurality_index([answer(1), answer(2), answer(1)], "portfolio") == 2


def test_plurality_ignores_unparseable_answers_and_reports_none_when_empty():
    assert plurality_index(["oops", answer(4)], "portfolio") == 1
    assert plurality_index(["oops", "also bad"], "portfolio") is None


def test_convergence_returns_first_answer_confirmed_by_its_successor():
    answers = [answer(1), answer(2), answer(2), answer(3)]
    assert convergence_index(answers, "portfolio") == 2  # confirmed at step 2
    # No confirmation: fall back to the final parseable answer.
    assert convergence_index([answer(1), answer(2), answer(3)], "portfolio") == 2


def test_convergence_does_not_confirm_across_unparseable_answers():
    answers = [answer(1), "bad", answer(1)]
    assert convergence_index(answers, "portfolio") == 2  # fallback, not confirmation


def test_checker_selects_feasible_highest_reward_using_only_statement_data():
    task = make_portfolio_tasks("dev", count=1, size=8)[0]
    optimum = list(task.optimal_selection())
    infeasible = list(range(len(task.rewards)))  # everything: violates capacity
    answers = [answer(*infeasible), answer(), answer(*optimum), answer()]
    assert checker_index(answers, task) == 2
    # No feasible candidate -> None rather than an arbitrary pick.
    assert checker_index([answer(*infeasible)], task) is None


def test_checker_ties_go_to_latest_candidate():
    task = make_portfolio_tasks("dev", count=1, size=8)[0]
    optimum = list(task.optimal_selection())
    assert checker_index([answer(*optimum), answer(*optimum)], task) == 1


def test_selector_indices_reports_every_rule_without_oracle_access():
    task = make_portfolio_tasks("dev", count=1, size=8)[0]
    answers = [answer(), answer(*task.optimal_selection())]
    chosen = selector_indices(answers, task, "portfolio")
    assert set(chosen) == {"first", "last", "plurality", "convergence", "checker"}
    assert chosen["first"] == 0 and chosen["last"] == 1
    with pytest.raises(ValueError):
        selector_indices([], task, "portfolio")


def test_summarize_counts_rescues_harms_and_missing_selections_paired_with_last():
    from evals.selection_study import summarize

    rows = [
        # last wrong, plurality right -> rescued
        {
            "error": None,
            "coverage": True,
            "passed": [True, False, False],
            "selected": {"last": 2, "plurality": 0, "convergence": 1},
        },
        # last right, plurality wrong -> harmed; convergence abstains -> failure
        {
            "error": None,
            "coverage": True,
            "passed": [False, False, True],
            "selected": {"last": 2, "plurality": 0, "convergence": None},
        },
        {"error": "RuntimeError"},
    ]
    summary = summarize(rows, ("last", "plurality", "convergence"))
    assert summary["trials"] == 3 and summary["completed"] == 2
    assert summary["coverage"] == 2
    assert summary["rules"]["last"]["passed"] == 1
    assert summary["rules"]["plurality"] == {
        "passed": 1,
        "rescued_vs_last": 1,
        "harmed_vs_last": 1,
        "none": 0,
    }
    assert summary["rules"]["convergence"]["none"] == 1
    assert summary["rules"]["convergence"]["passed"] == 0


async def test_runner_uses_dev_split_hides_oracle_and_saves_candidates(tmp_path):
    from unittest.mock import AsyncMock, patch

    from evals.selection_study import run

    task = make_portfolio_tasks("dev", count=1, size=8)[0]
    good = json.dumps({"selected": list(task.optimal_selection())})
    calls = AsyncMock(side_effect=['{"selected": []}', good, good])
    with patch("evals.selection_study.wf.agent", calls):
        report = await run(tmp_path / "s.json", ["google:test"], count=1, steps=3)
    row = report["rows"][0]
    assert row["passed"] == [False, True, True] and row["coverage"] is True
    assert row["selected"]["first"] == 0 and row["selected"]["last"] == 2
    assert row["selected"]["plurality"] == 2  # {good} x2 beats {} x1
    assert row["selected"]["convergence"] == 2
    assert row["selected"]["checker"] == 2
    assert report["summary"]["rules"]["plurality"]["rescued_vs_last"] == 0
    prompts = [c.args[0] for c in calls.await_args_list]
    assert all(prompt.startswith(task.statement) for prompt in prompts)
    assert (
        good not in prompts[0]
    )  # the first call cannot see any answer, let alone the optimum
    with pytest.raises(ValueError):
        await run(tmp_path / "h.json", ["google:test"], split="heldout")
