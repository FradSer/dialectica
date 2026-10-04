"""Given invalid judge measurements, fail explicitly rather than inventing ties."""

from unittest.mock import AsyncMock, patch

import pytest

from evals.judge import BlindJudge, parse_judge_verdict


@pytest.mark.parametrize("winner", ["banana", "engine", "baseline", 42])
def test_invalid_winner_is_a_failed_measurement(winner):
    import json

    verdict = parse_judge_verdict(
        json.dumps({"winner": winner, "reasoning": "invalid"})
    )
    assert verdict.parse_failed


async def test_exhausted_judge_errors_do_not_become_ties():
    call = AsyncMock(return_value="not a verdict")
    with (
        patch("dialectica.agent_runtime.run_agent", call),
        pytest.raises(RuntimeError, match="judge"),
    ):
        await BlindJudge(object()).compare("problem", "first", "second")
    assert call.await_count == 3
