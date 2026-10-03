"""Live end-to-end tests against the configured real model (Gemini by default).

Deselected by default (``addopts = -m 'not e2e'``). Run explicitly with:

    uv run pytest -m e2e

Skipped when the selected provider's credentials are absent (loaded from .env
via conftest). This is the slow/realistic counterpart to the mocked tests —
exercises the shipped production API (``create_repair_engine``), not a
demoted reference pattern.
"""

import os
import secrets
from threading import get_ident

import pytest
from pydantic import BaseModel

from dialectica import TokenUsage, Workflow, create_repair_engine
from dialectica import workflow as wf

_openai_selected = os.getenv("DEFAULT_MODEL_CONFIG", "").startswith("openai:")
_live_ready = (
    bool(os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"))
    if _openai_selected
    else bool(os.getenv("GOOGLE_API_KEY"))
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _live_ready,
        reason="selected live provider credentials are absent",
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


class LookupAnswer(BaseModel):
    value: int


@pytest.mark.parametrize("workers", [None, "2"])
async def test_live_tools_schema_and_sync_worker_execution(monkeypatch, workers):
    """Given a value only known to a tool, the live model must retrieve it.

    When tools and schema are combined, the returned Pydantic result contains
    that value. With workers enabled the sync tool executes off the event loop.
    """
    value = secrets.randbelow(900_000_000) + 100_000_000
    caller_thread = get_ident()
    tool_threads: list[int] = []
    if workers is None:
        monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    else:
        monkeypatch.setenv("DIALECTICA_TOOL_WORKERS", workers)
    monkeypatch.setenv("DIALECTICA_MAX_LLM_CALLS", "8")

    def lookup() -> dict[str, int]:
        """Return the current value. Call this to obtain the answer."""
        tool_threads.append(get_ident())
        return {"value": value}

    async def script() -> tuple[LookupAnswer, TokenUsage]:
        answer = await wf.agent(
            "Call lookup to retrieve the current value, then return it as JSON. "
            "Never invent the value; it is only available through lookup.",
            schema=LookupAnswer,
            tools=[lookup],
            max_attempts=1,
        )
        return answer, wf.budget().usage()

    answer, usage = await Workflow(script).run()
    assert answer == LookupAnswer(value=value)
    assert tool_threads, "live model did not execute the tool"
    assert all(
        (thread != caller_thread) == (workers is not None) for thread in tool_threads
    )
    assert usage.total_tokens > 0, "live backend did not report token usage"
