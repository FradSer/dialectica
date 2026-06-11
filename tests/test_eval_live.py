"""Live end-to-end test of the eval harness against the real Gemini API.

Deselected by default (``addopts = -m 'not e2e'``). Run explicitly with:

    uv run pytest -m e2e

Skipped automatically when GOOGLE_API_KEY is absent (loaded from .env via
conftest). Uses a deliberately small engine configuration to keep cost low.
"""

import os

import pytest

from dialectica import create_engine
from evals.baseline import SingleCallBaseline, create_baseline_agent
from evals.harness import run_eval
from evals.judge import BlindJudge, create_judge_agent
from evals.problems import EvalProblem

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY not set (configure dialectica/.env)",
    ),
]


async def test_live_eval_compares_engine_and_baseline():
    problems = [
        EvalProblem(
            id="cloud-costs",
            statement="How can a small team reduce cloud infrastructure costs?",
        )
    ]

    def engine_factory(statement: str):
        return create_engine(
            statement,
            max_depth=1,
            beam_width=2,
            max_gan_rounds=1,
            score_threshold=6.0,
        )

    report = await run_eval(
        problems,
        engine_factory=engine_factory,
        baseline=SingleCallBaseline(create_baseline_agent()),
        judge=BlindJudge(create_judge_agent()),
    )

    result = report.results[0]
    assert result.winner in {"engine", "baseline", "tie"}
    assert len(result.engine_answer) > 50
    assert len(result.baseline_answer) > 50
    assert result.baseline_calls == 1
    assert result.engine_calls > result.baseline_calls
    assert report.engine_wins + report.baseline_wins + report.ties == 1
