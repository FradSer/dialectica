"""Given constrained task families, hidden verifiers reject plausible wrong plans."""

import json

from evals.research_tasks import PortfolioTask, make_portfolio_tasks


def test_portfolio_verifier_checks_feasibility_and_global_optimum():
    task = PortfolioTask("manual", (4, 7, 5), (2, 4, 3), 5, ((0, 1),))
    assert task.verify(json.dumps({"selected": [0, 2]})) == (True, "")
    assert not task.verify(json.dumps({"selected": [1]}))[0]
    assert not task.verify(json.dumps({"selected": [0, 1]}))[0]
    assert not task.verify(json.dumps({"selected": [0, 0]}))[0]
    assert not task.verify("not JSON")[0]


def test_generated_tasks_are_deterministic_and_splits_disjoint():
    dev = make_portfolio_tasks("dev", count=8)
    held = make_portfolio_tasks("heldout", count=16)
    assert dev == make_portfolio_tasks("dev", count=8)
    assert {t.task_id for t in dev}.isdisjoint(t.task_id for t in held)
    assert {t.rewards for t in dev}.isdisjoint(t.rewards for t in held)
    for task in dev + held:
        assert task.verify(json.dumps({"selected": task.optimal_selection()}))[0]
        assert (
            str(task.optimal_value()) not in task.statement.split("Hidden optimum:")[-1]
            if "Hidden optimum:" in task.statement
            else True
        )


def test_formatting_and_substantive_correctness_are_separate():
    task = PortfolioTask("manual", (4, 7, 5), (2, 4, 3), 5, ((0, 1),))
    wrapped = '```json\n{"selected": [0, 2]}\n```'
    assert not task.verify(wrapped)[0]
    assert task.verify_content(wrapped) == (True, "")
    assert not task.verify_content('```json\n{"selected": [1]}\n```')[0]
    assert not task.verify_content('Narrative {"selected": [0, 2]}')[0]
