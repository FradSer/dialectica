"""Matched single tool-agent (self-repair allowed) vs fixed structured workflow.

Offline is a plumbing smoke test with known reference patches, never evidence of
model quality. Live calls require --live, an explicit model/version and turn cap;
provider credentials must already exist in the host environment. No .env loading.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from dialectica import workflow as wf
from dialectica.agent_runtime import AgentResponse, TokenUsage, model_call_guard
from evals.workflow_bug_fixtures import FIXTURES, BugFixture
from examples.bugfix_workflow import BugfixHost, structured_bugfix


def prepare(root: Path, fixture: BugFixture) -> BugfixHost:
    root.mkdir(parents=True, exist_ok=False)
    (root / "target.py").write_text(fixture.broken)
    assertions = "\n".join(
        "        " + line for line in fixture.assertions.splitlines()
    )
    (root / "test_target.py").write_text(
        "import unittest\nfrom target import *\n\nclass Regression(unittest.TestCase):\n"
        "    def test_regression(self):\n" + assertions + "\n"
    )
    return BugfixHost(root)


async def run_arm(root, fixture, arm, config):
    host = prepare(root, fixture)
    started = time.monotonic()
    initial = await asyncio.to_thread(host.verify)
    problem = (
        fixture.description
        + "\nExisting failure:\n"
        + initial.feedback
        + "\nUse read_file, write_file and run_tests. Keep test_target.py unchanged. "
        "Fix target.py, run the tests, and repair failures before finishing."
    )

    async def script():
        if arm == "single":
            # The single agent receives identical tools/tests and can iterate in
            # its tool loop until the SAME shared model-turn cap is exhausted.
            await wf.agent(
                problem, tools=host.tools, model=config.model, label="single"
            )
            return await asyncio.to_thread(host.verify)
        return await structured_bugfix(problem, host, config.model)

    async def offline_agent(agent, instruction):
        guard = model_call_guard.get()
        if guard:
            guard()
        # Reference patch is visible only to this clearly labelled smoke adapter.
        if agent.name != "diagnose":
            host.tools[1](fixture.fixed)
        host.tools[0]("target.py")
        await asyncio.to_thread(host.tools[2])
        return AgentResponse("offline reference adapter", TokenUsage())

    run = wf.Workflow(
        script,
        journal_dir=root / "journals",
        budget_total=6,
        model_turn_limit=config.turn_limit,
        concurrency=1,
    )
    error = None
    try:
        if initial.status != "fail":
            raise RuntimeError("Fixture must have a reproducible initial test failure")
        if config.live:
            await asyncio.wait_for(run.run(), config.timeout)
        else:
            with patch("dialectica.agent_runtime.run_agent", offline_agent):
                await asyncio.wait_for(run.run(), config.timeout)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    final = await asyncio.to_thread(host.verify)
    diff = host.diff()
    (root / "patch.diff").write_text(diff)
    (root / "tests.json").write_text(json.dumps(host.test_runs, indent=2))
    report = run.report
    record = {
        "fixture": fixture.id,
        "provenance": fixture.provenance,
        "arm": arm,
        "mode": "live" if config.live else "offline_smoke",
        "model": config.model,
        "model_version": config.model_version,
        "model_version_note": "host-supplied identifier; pin immutable provider revisions when available",
        "turn_limit": config.turn_limit,
        "agent_step_limit": 6,
        "tools": ["read_file", "write_file", "run_tests"],
        "test_feedback": "identical visible regression tests and initial failure",
        "initial_status": initial.status,
        "final_status": final.status,
        "completed": bool(
            not error
            and report
            and report.status == "completed"
            and initial.status == "fail"
            and final.status == "pass"
            and diff
        ),
        "workflow_status": report.status if report else "not_started",
        "error": error,
        "human_interventions": 0,
        "elapsed_seconds": time.monotonic() - started,
        "usage": asdict(report.usage) if config.live and report else None,
        "cost_usd": None,
        "cost_note": "unknown; attach provider billing receipts; never inferred from missing usage",
        "patch_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "python": platform.python_version(),
        "runtime_settings": {
            name: os.environ.get(name)
            for name in (
                "DIALECTICA_DISABLE_THINKING",
                "DIALECTICA_MAX_LLM_CALLS",
                "DIALECTICA_CONTEXT_CACHE",
                "DIALECTICA_TOOL_WORKERS",
            )
        },
        "fixture_sha256": hashlib.sha256(
            (fixture.broken + fixture.assertions).encode()
        ).hexdigest(),
        "lockfile_sha256": hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "uv.lock").read_bytes()
        ).hexdigest(),
        "test_command": host.test_runs[0]["command"],
    }
    (root / "result.json").write_text(json.dumps(record, indent=2))
    return record


async def main(config):
    config.output.mkdir(parents=True, exist_ok=False)
    fixtures = (
        FIXTURES
        if config.fixture == "all"
        else [f for f in FIXTURES if f.id == config.fixture]
    )
    records = []
    rng = random.Random(config.seed)
    for fixture in fixtures:
        arms = ["single", "workflow"]
        rng.shuffle(arms)  # paired fresh workspaces, deterministic randomized order
        for arm in arms:
            record = await run_arm(
                config.output / fixture.id / arm, fixture, arm, config
            )
            records.append(record)
            print(json.dumps(record), flush=True)
    summary = {
        "mode": "live" if config.live else "offline_smoke",
        "quality_claim": "No model effectiveness claim from offline smoke results",
        "seed": config.seed,
        "records": records,
        "arms": {
            arm: {
                "completed": sum(r["completed"] for r in records if r["arm"] == arm),
                "total": sum(r["arm"] == arm for r in records),
                "human_interventions": sum(
                    r["human_interventions"] for r in records if r["arm"] == arm
                ),
                "elapsed_seconds": sum(
                    r["elapsed_seconds"] for r in records if r["arm"] == arm
                ),
            }
            for arm in ("single", "workflow")
        },
    }
    (config.output / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0 if all(r["completed"] for r in records) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fixture", choices=["all", *(f.id for f in FIXTURES)], default="all"
    )
    parser.add_argument(
        "--live", action="store_true", help="Explicitly authorize paid model calls"
    )
    parser.add_argument("--model", default="google:offline-smoke")
    parser.add_argument("--model-version", default="offline-reference-adapter-v1")
    parser.add_argument("--turn-limit", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--seed", type=int, default=0)
    config = parser.parse_args()
    if config.live and (
        config.model == "google:offline-smoke"
        or config.model_version == "offline-reference-adapter-v1"
    ):
        parser.error("--live requires explicit --model and --model-version")
    if config.turn_limit < 1 or config.timeout <= 0:
        parser.error("turn-limit and timeout must be positive")
    sys.exit(asyncio.run(main(config)))
