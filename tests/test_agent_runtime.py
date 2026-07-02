"""Unit tests for agent_runtime's token metering pieces.

No ADK internals are patched: ``_usage_from_events`` is a pure function tested
against Event objects constructed in-memory, and ``AgentResponse`` is a plain
str subclass.
"""

from google.adk.events import Event
from google.genai import types

from dialectica.agent_runtime import AgentResponse, TokenUsage, _usage_from_events


def test_usage_from_events_sums_metadata_across_events():
    """Tool-using calls produce several LLM turns; usage must sum across all
    events, treat missing metadata as zero, and count thinking as output."""
    events = [
        Event(
            author="agent",
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10,
                candidates_token_count=5,
                thoughts_token_count=2,
                total_token_count=17,
            ),
        ),
        Event(author="agent"),  # e.g. a function-call event without usage
        Event(
            author="agent",
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=20,
                candidates_token_count=8,
                total_token_count=28,
            ),
        ),
    ]
    assert _usage_from_events(events) == TokenUsage(
        prompt_tokens=30, output_tokens=15, total_tokens=45
    )


def test_usage_from_events_empty_is_zero():
    assert _usage_from_events([]) == TokenUsage()


def test_usage_from_events_litellm_shape_does_not_double_count_reasoning():
    """ADK's LiteLLM mapping sets candidates_token_count = completion_tokens
    (which already INCLUDES reasoning) and also reports thoughts_token_count.
    The totals disambiguate: total - prompt - candidates leaves no room for
    thoughts, so output must be 9, not 13."""
    events = [
        Event(
            author="agent",
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10,
                candidates_token_count=9,
                thoughts_token_count=4,
                total_token_count=19,
            ),
        ),
    ]
    assert _usage_from_events(events) == TokenUsage(
        prompt_tokens=10, output_tokens=9, total_tokens=19
    )


def test_usage_from_events_without_total_keeps_candidates_plus_thoughts():
    """No total reported -> nothing to disambiguate with; keep the native
    Gemini reading (candidates excludes thoughts)."""
    events = [
        Event(
            author="agent",
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10,
                candidates_token_count=5,
                thoughts_token_count=2,
            ),
        ),
    ]
    assert _usage_from_events(events).output_tokens == 7


def test_agent_response_is_a_str_carrying_usage():
    """The run_agent seam contract stays ``-> str``: every existing consumer
    (and every fake returning a plain str) must keep working unchanged."""
    usage = TokenUsage(prompt_tokens=3, output_tokens=2, total_tokens=5)
    response = AgentResponse("  hello  ", usage)
    assert isinstance(response, str)
    assert response.usage == usage
    assert response.strip() == "hello"


def test_agent_response_survives_a_pickle_round_trip():
    import pickle

    usage = TokenUsage(prompt_tokens=3, output_tokens=2, total_tokens=5)
    restored = pickle.loads(pickle.dumps(AgentResponse("hello", usage)))
    assert restored == "hello"
    assert restored.usage == usage
