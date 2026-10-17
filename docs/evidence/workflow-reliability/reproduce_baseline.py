import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from dialectica import create_repair_engine
from dialectica import workflow as wf
from dialectica.agent_runtime import AgentResponse, TokenUsage
from dialectica.workflow_journal import agent_cache_key, script_fingerprint

root = Path(__file__).parent


async def partial():
    async def ok():
        return "kept"

    async def bad():
        raise ValueError("failure evidence")

    return await wf.parallel([ok, bad])


calls = []


async def fake(agent, instruction):
    calls.append(instruction)
    await asyncio.sleep(0)
    return AgentResponse("candidate", TokenUsage(output_tokens=10, model_calls=1))


async def queued():
    await wf.parallel([lambda: wf.agent("one"), lambda: wf.agent("two")])
    return {
        "dispatched": list(calls),
        "reported_output_tokens": wf.budget().spent_tokens(),
    }


async def repair():
    return await create_repair_engine(
        "verify", verifier=lambda answer: ("yes", ""), max_attempts=1
    ).run()


async def main():
    with (
        patch("dialectica.workflow.get_model_config", return_value="offline"),
        patch("dialectica.agent_runtime.run_agent", fake),
    ):
        out = {
            "partial_failure_result": await wf.Workflow(
                partial, journal_dir=root / "journals"
            ).run()
        }
        out["token_budget_10_concurrency_1"] = await wf.Workflow(
            queued,
            journal_dir=root / "journals",
            budget_total=10,
            budget_unit="tokens",
            concurrency=1,
        ).run()
        result = await wf.Workflow(repair, journal_dir=root / "journals").run()
        out["non_boolean_verifier_accepted"] = {
            "passed": result["passed"],
            "type": type(result["passed"]).__name__,
        }

    def script():
        return 1

    old = script_fingerprint(script)

    def script():
        return 2

    out["changed_script_same_fingerprint"] = old == script_fingerprint(script)

    def key(tool):
        return agent_cache_key(
            "p",
            schema=None,
            tools=[tool],
            instructions="",
            label=None,
            phase=None,
            model="fixed",
            isolation=None,
            agent_type=None,
        )

    def factory():
        def read():
            return 1

        return read

    first, second = factory(), factory()
    out["equivalent_tool_instances_different_key"] = key(first) != key(second)
    print(json.dumps(out, indent=2))


asyncio.run(main())
