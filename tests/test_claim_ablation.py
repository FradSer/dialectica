"""Given fixed candidates, selection diagnostics never supply oracle feedback."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from evals.claim_ablation import answer_key, run
from evals.research_tasks import make_portfolio_tasks
from examples.patterns.claim_falsification_pattern import ClaimCandidate, ClaimVerdicts


def test_answer_equivalence_preserves_invalid_or_distinct_selections():
    assert answer_key('{"selected": [2, 1]}') == answer_key(
        '```json\n{"selected": [1, 2]}\n```'
    )
    assert answer_key('{"selected": [1, 1]}') != answer_key('{"selected": [1]}')
    with pytest.raises(ValueError, match="unparseable"):
        answer_key("bad answer")


async def test_report_saves_coverage_selection_and_inconclusive_errors(tmp_path):
    task = make_portfolio_tasks("dev", 1, 4)[0]
    good = ClaimCandidate(
        answer=json.dumps({"selected": task.optimal_selection()}), claims=["c"] * 5
    )
    bad = ClaimCandidate(answer='{"selected": []}', claims=["c"] * 5)
    # Single succeeds; consensus has an outvoted correct candidate; refinement
    # measurement fails; CLR rescues the same minority through assessment.
    calls = AsyncMock(
        side_effect=[
            good,
            bad,
            good,
            bad,
            bad,
            None,
            bad,
            good,
            ClaimVerdicts(survived=[False] * 5),
            ClaimVerdicts(survived=[True] * 5),
        ]
    )
    output = tmp_path / "result.json"
    with (
        patch("evals.claim_ablation.wf.agent", calls),
        patch("evals.claim_ablation.random.Random.shuffle", return_value=None),
    ):
        report = await run(output, ["openai:test"], "dev", 1, 4, samples=2)
    single, consensus, refine, claims = report["rows"]
    assert single["passed"]
    assert consensus["coverage"] and not consensus["passed"]
    assert refine["passed"] is None
    assert refine["receipt"]["error"] == "TypeError"
    assert claims["passed"] and claims["coverage"]
    assert not claims["same_candidate_consensus_passed"]
    assert json.loads(output.read_text()) == report
    for call in calls.await_args_list:
        assert "Hidden optimum" not in call.args[0]
        assert "subset is feasible but" not in call.args[0]


async def test_seeded_arm_order_and_partial_arm_protocol(tmp_path):
    async def fake_call(*args, **kwargs):
        if kwargs.get("schema") is ClaimVerdicts:
            return ClaimVerdicts(survived=[True] * 5)
        return ClaimCandidate(answer='{"selected": []}', claims=["c"] * 5)

    with patch("evals.claim_ablation.wf.agent", AsyncMock(side_effect=fake_call)):
        first = await run(
            tmp_path / "a.json",
            ["google:test"],
            "dev",
            2,
            4,
            samples=1,
            repeats=2,
            order_seed=10431,
        )
        second = await run(
            tmp_path / "b.json",
            ["google:test"],
            "dev",
            2,
            4,
            samples=1,
            repeats=2,
            order_seed=10431,
        )
        single = await run(
            tmp_path / "c.json",
            ["google:test"],
            "dev",
            1,
            4,
            arms=("single",),
            order_seed=10431,
        )
    assert [row["arm"] for row in first["rows"]] == [
        row["arm"] for row in second["rows"]
    ]
    orders = {tuple(row["order"]) for row in first["rows"]}
    assert len(orders) > 1
    assert all(
        set(order) == {"single", "consensus", "self_refine", "claims"}
        for order in orders
    )
    assert single["arms"] == ["single"] and len(single["rows"]) == 1
    assert first["allowance_unit"] == "workflow_agent_steps"
    assert not first["token_parity"] and not first["dollar_parity"]
