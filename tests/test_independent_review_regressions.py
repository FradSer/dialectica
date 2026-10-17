"""Offline reproductions from the independent review of PR #10."""

import asyncio

import pytest

from dialectica import workflow as wf
from dialectica.tool_policy import tool_capability


@pytest.mark.parametrize("tail_first", [False, True])
async def test_parallel_verification_invalidates_cached_suffix(
    tmp_path, monkeypatch, tail_first
):
    holder = {}
    calls = []
    resumed = False
    tail_started = asyncio.Event()
    first_reran = asyncio.Event()

    async def fake(agent, instruction):
        calls.append(instruction)
        if resumed and instruction == "first":
            first_reran.set()
        return instruction + ("-fresh" if resumed else "-old")

    async def verify_first(result):
        await tail_started.wait()
        if tail_first:
            await asyncio.sleep(0)
        return False

    async def verify_tail(result):
        tail_started.set()
        if not tail_first:
            await first_reran.wait()
        return True

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [
                lambda: wf.agent(
                    "first", replay_version="1", verify_cached=verify_first
                ),
                lambda: wf.agent("tail", replay_version="1", verify_cached=verify_tail),
            ]
        )

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    assert await wf.Workflow(
        script, journal_dir=tmp_path, resume_version="1"
    ).run() == ["first-old", "tail-old"]
    calls.clear()
    resumed = True
    result = await asyncio.wait_for(
        wf.Workflow(
            script,
            journal_dir=tmp_path,
            resume_version="1",
            resume_run_id=holder["id"],
        ).run(),
        2,
    )
    assert result == ["first-fresh", "tail-fresh"]
    assert calls == ["first", "tail"]


@pytest.mark.parametrize("rejection", ["budget", "permissions", "resume"])
async def test_caught_preflight_rejection_is_partial(tmp_path, monkeypatch, rejection):
    holder = {}
    resumed = False

    def tool():
        return "external"

    async def fake(agent, instruction):
        return "ok"

    async def script():
        holder["id"] = wf.run_id()
        try:
            await wf.agent(
                "step",
                tools=[tool] if rejection != "budget" else None,
                agent_type="Explore" if rejection == "permissions" else None,
            )
        except (wf.BudgetExhausted, PermissionError, wf.ResumeUnsafeError):
            assert rejection != "resume" or resumed
        return "handled"

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    config = {"journal_dir": tmp_path, "resume_version": "1"}
    if rejection == "resume":
        await wf.Workflow(script, **config).run()
        config["resume_run_id"] = holder["id"]
        resumed = True
    if rejection == "budget":
        config["budget_total"] = 0
    run = wf.Workflow(script, **config)
    assert await run.run() == "handled"
    assert run.report.status == "partial"
    assert len(run.report.outcomes) == 1
    assert (
        run.report.outcomes[0].error_type
        == {
            "budget": "BudgetExhausted",
            "permissions": "PermissionError",
            "resume": "ResumeUnsafeError",
        }[rejection]
    )
    assert run.report.outcomes[0].traceback


async def test_cached_agent_restores_declared_phase(tmp_path, monkeypatch):
    holder = {}
    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        return "ok"

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("step", phase="Investigate")

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    config = {
        "journal_dir": tmp_path,
        "resume_version": "1",
        "meta": {
            "name": "phase-test",
            "description": "phase-test",
            "phases": [{"title": "Investigate"}],
        },
    }
    await wf.Workflow(script, **config).run()
    assert await wf.Workflow(script, resume_run_id=holder["id"], **config).run() == "ok"
    assert calls == ["step"]


async def test_invalidated_external_suffix_is_refused_without_repeating_effect(
    tmp_path, monkeypatch
):
    holder = {}
    tail_started = asyncio.Event()
    calls = []

    @tool_capability(access="write", version="1")
    def external():
        return "effect"

    async def fake(agent, instruction):
        calls.append(instruction)
        return "ok"

    async def verify_first(result):
        await tail_started.wait()
        return False

    async def verify_tail(result):
        tail_started.set()
        return True

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [
                lambda: wf.agent(
                    "first", replay_version="1", verify_cached=verify_first
                ),
                lambda: wf.agent(
                    "external",
                    tools=[external],
                    replay_version="1",
                    verify_cached=verify_tail,
                ),
            ],
            errors="collect",
        )

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    await wf.Workflow(script, journal_dir=tmp_path, resume_version="1").run()
    calls.clear()
    run = wf.Workflow(
        script,
        journal_dir=tmp_path,
        resume_version="1",
        resume_run_id=holder["id"],
    )
    outcomes = await asyncio.wait_for(run.run(), 2)
    assert calls == ["first"]
    assert outcomes[1].error_type == "ResumeUnsafeError"
    assert run.report.status == "partial"


async def test_cancelled_prefix_releases_cached_suffix_without_stale_reuse(
    tmp_path, monkeypatch
):
    holder = {}
    calls = []
    tail_started = asyncio.Event()
    release_tail = asyncio.Event()

    async def fake(agent, instruction):
        calls.append(instruction)
        return instruction

    async def verify_first(result):
        await tail_started.wait()
        raise asyncio.CancelledError()

    async def verify_tail(result):
        tail_started.set()
        await release_tail.wait()
        return True

    async def first():
        try:
            return await wf.agent(
                "first", replay_version="1", verify_cached=verify_first
            )
        except asyncio.CancelledError:
            release_tail.set()
            return "cancelled"

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [
                first,
                lambda: wf.agent("tail", replay_version="1", verify_cached=verify_tail),
            ]
        )

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    await wf.Workflow(script, journal_dir=tmp_path, resume_version="1").run()
    calls.clear()
    run = wf.Workflow(
        script,
        journal_dir=tmp_path,
        resume_version="1",
        resume_run_id=holder["id"],
    )
    assert await asyncio.wait_for(run.run(), 2) == ["cancelled", "tail"]
    assert calls == ["tail"]
    assert run.report.status == "partial"


async def test_verifier_agent_reentry_is_refused_without_deadlock(
    tmp_path, monkeypatch
):
    holder = {}
    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        return "ok"

    async def verify(result):
        await wf.agent("nested-verifier-agent")
        return True

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("first", replay_version="1", verify_cached=verify)

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    await wf.Workflow(script, journal_dir=tmp_path, resume_version="1").run()
    calls.clear()
    run = wf.Workflow(
        script,
        journal_dir=tmp_path,
        resume_version="1",
        resume_run_id=holder["id"],
    )
    assert await asyncio.wait_for(run.run(), 2) == "ok"
    assert calls == ["first"]
    assert run.report.status == "partial"
    assert run.report.outcomes[0].error_type == "RuntimeError"
