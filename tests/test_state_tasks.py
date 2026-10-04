"""Given evolving registers, verification checks exact state rather than formatting."""

import json

from evals.research_tasks import StateTask, make_state_tasks


def test_state_operations_use_precise_snapshot_and_modulo_semantics():
    task = StateTask(
        "manual",
        (95, 4, 10),
        (("add", 0, 1, 5), ("move", 1, 2, 7), ("if_add", 1, 2, 5), ("swap", 0, 2, 0)),
    )
    # add -> (3,4,10); move -> (3,94,17); if_add -> (3,2,17); swap -> (17,2,3)
    assert task.final_state() == (17, 2, 3)
    assert task.verify_content('```json\n{"state": [17, 2, 3]}\n```') == (True, "")
    for value in ([17, 2, 4], [17, 2], [True, 2, 3], [17, 2, 100]):
        assert not task.verify(json.dumps({"state": value}))[0]


def test_state_task_generation_is_deterministic_and_splits_disjoint():
    dev = make_state_tasks("dev", 4, steps=24)
    held = make_state_tasks("heldout", 4, steps=24)
    assert dev == make_state_tasks("dev", 4, steps=24)
    assert {t.operations for t in dev}.isdisjoint(t.operations for t in held)
    for task in dev + held:
        assert task.verify(json.dumps({"state": task.final_state()}))[0]
        assert "Expected final state" not in task.statement
