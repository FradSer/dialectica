"""Step definitions for features/resilience.feature.

These exercise the retry loop inside ``agent_runtime.run_agent`` itself, so
they patch the one private transport seam below it (``_call_agent_once``)
rather than ``run_agent`` — patching ``run_agent`` would bypass the behavior
under test.
"""

import asyncio
from unittest.mock import patch

from pytest_bdd import given, parsers, scenarios, then, when

from dialectica import agent_runtime

scenarios("features/resilience.feature")


class FlakyTransport:
    """Async ``_call_agent_once`` stand-in failing ``failures`` times first."""

    def __init__(self, failures: int):
        self.failures = failures
        self.attempts = 0

    async def __call__(self, agent, instruction: str) -> str:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("transient network failure")
        return "ok"


@given(
    parsers.parse("an LLM transport that fails {n:d} times before succeeding"),
    target_fixture="transport",
)
def flaky_transport(n: int):
    return FlakyTransport(failures=n)


@given("an LLM transport that always fails", target_fixture="transport")
def always_failing_transport():
    return FlakyTransport(failures=10**6)


@when("an agent call runs through the runtime", target_fixture="outcome")
def run_call(transport):
    async def go():
        return await agent_runtime.run_agent(None, "x", max_attempts=3, base_delay=0)

    with patch("dialectica.agent_runtime._call_agent_once", transport):
        try:
            return {"result": asyncio.run(go()), "error": None}
        except ConnectionError as e:
            return {"result": None, "error": e}


@then(parsers.parse("the call succeeds after {n:d} attempts"))
def call_succeeds(outcome, transport, n: int):
    assert outcome["error"] is None
    assert outcome["result"] == "ok"
    assert transport.attempts == n


@then(parsers.parse("the call fails after exhausting {n:d} attempts"))
def call_fails(outcome, transport, n: int):
    assert outcome["result"] is None
    assert isinstance(outcome["error"], ConnectionError)
    assert transport.attempts == n
