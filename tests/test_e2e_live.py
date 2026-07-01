"""Live end-to-end test against the real Gemini API.

Deselected by default (``addopts = -m 'not e2e'``). Run explicitly with:

    uv run pytest -m e2e

Skipped automatically when GOOGLE_API_KEY is absent (loaded from .env via
conftest). This is the slow/realistic counterpart to the mocked tests —
exercises the shipped production API (``create_repair_engine``), not a
demoted reference pattern.
"""

import os

import pytest

from dialectica import create_repair_engine

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY not set (configure dialectica/.env)",
    ),
]


async def test_live_repair_engine_produces_a_verified_answer():
    def verifier(answer: str) -> tuple[bool, str]:
        return bool(answer.strip()), "empty answer"

    engine = create_repair_engine(
        problem="How can a small team reduce cloud infrastructure costs?",
        verifier=verifier,
        max_attempts=2,
    )
    result = await engine.run()

    assert isinstance(result["final_answer"], str)
    assert len(result["final_answer"]) > 50
    assert result["passed"] is True
    assert result["attempts"] >= 1
