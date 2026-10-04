"""Controlled comparisons preserve ordering, oracle isolation and exact state keys."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from evals.meta_ablation import prediction_key, run
from evals.research_tasks import make_state_tasks


def test_equivalence_respects_task_semantics():
    assert prediction_key('{"selected": [2,1]}', "portfolio") == (1, 2)
    assert prediction_key('{"state": [2,1]}', "state") == (2, 1)
    with pytest.raises(ValueError):
        prediction_key('{"state": [true,1]}', "state")


async def test_state_reports_are_reproducibly_ordered_and_oracle_is_hidden(tmp_path):
    task = make_state_tasks("dev", 1, steps=2)[0]
    answer = json.dumps({"state": task.final_state()})
    calls = AsyncMock(return_value=answer)
    with patch("evals.meta_ablation.wf.agent", calls):
        first = await run(
            tmp_path / "first.json",
            ["google:test"],
            count=1,
            family="state",
            difficulty=2,
            allowance=2,
            arms=("single", "consensus"),
        )
        second = await run(
            tmp_path / "second.json",
            ["google:test"],
            count=1,
            family="state",
            difficulty=2,
            allowance=2,
            arms=("single", "consensus"),
        )
    assert [row["arm"] for row in first["rows"]] == [
        row["arm"] for row in second["rows"]
    ]
    assert all(row["passed"] and row["coverage"] for row in first["rows"])
    assert calls.await_count == 6
    assert json.loads((tmp_path / "first.json").read_text()) == first
    for call in calls.await_args_list:
        assert task.statement in call.args[0]
        assert "final register state is incorrect" not in call.args[0]


async def test_protocol_is_saved_before_first_call_and_existing_run_is_preserved(
    tmp_path,
):
    """Given a run, freeze its inputs before dispatch; reruns cannot erase evidence."""
    output = tmp_path / "frozen.json"
    protocol_path = output.with_suffix(".protocol.json")

    async def checked_call(*args, **kwargs):
        protocol = json.loads(protocol_path.read_text())
        assert protocol["configuration"]["split"] == "heldout"
        assert protocol["task_digest"]
        assert protocol["source_digests"]["evals/meta_ablation.py"]
        assert json.loads(output.read_text())["rows"] == []
        return '{"state": [0,0,0,0,0,0]}'

    with patch("evals.meta_ablation.wf.agent", AsyncMock(side_effect=checked_call)):
        report = await run(
            output,
            ["google:test"],
            split="heldout",
            count=1,
            family="state",
            difficulty=2,
            arms=("single",),
        )
    assert report["rows"][0]["receipt"]["error"] is None
    saved = output.read_bytes()
    with patch("evals.meta_ablation.wf.agent", AsyncMock()) as calls:
        with pytest.raises(FileExistsError):
            await run(
                output,
                ["google:test"],
                count=1,
                family="state",
                difficulty=2,
                arms=("single",),
            )
        calls.assert_not_awaited()
    assert output.read_bytes() == saved
