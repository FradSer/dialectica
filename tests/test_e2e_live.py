"""Live end-to-end test against the real Gemini API.

Deselected by default (``addopts = -m 'not e2e'``). Run explicitly with:

    uv run pytest -m e2e

Skipped automatically when GOOGLE_API_KEY is absent (loaded from .env via
conftest). This is the slow/realistic counterpart to the mocked tests.
"""

import os

import pytest

from dialectica import create_coordinator

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY not set (configure dialectica/.env)",
    ),
]


async def test_live_tot_workflow_produces_answer():
    coordinator = create_coordinator(
        problem="How can a small team reduce cloud infrastructure costs?",
        max_depth=2,
        beam_width=2,
        max_gan_rounds=1,
        score_threshold=6.0,
    )
    result = await coordinator.run()

    assert isinstance(result["final_answer"], str)
    assert len(result["final_answer"]) > 50
    assert result["stats"]["total_thoughts"] > 0
    assert result["best_path"][0] == "root"

    # at least one thought should have been adversarially scored
    scored = [t for t in coordinator.thought_tree.values() if t.evaluationScore is not None]
    assert scored, "expected at least one GAN-evaluated thought"
