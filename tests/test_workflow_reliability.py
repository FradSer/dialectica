"""Executable reliability contracts; all model calls are offline fakes."""

import asyncio
import subprocess
from pathlib import Path

import pytest

from dialectica.agent_factory import create_agent
from dialectica.workflow_journal import agent_cache_key
from dialectica.workflow_worktree import worktree_path, worktree_session


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
    )
    return tmp_path


async def test_concurrent_worktrees_never_change_process_cwd(git_repo, monkeypatch):
    tmp_path = git_repo
    monkeypatch.chdir(tmp_path)
    original = Path.cwd()
    ready = asyncio.Event()
    entered = 0

    async def worker(label):
        nonlocal entered
        async with worktree_session(label=label, run_id="concurrent") as handle:
            entered += 1
            if entered == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 2)
            assert Path.cwd() == original
            assert worktree_path.get() == handle.path
            return handle.path

    paths = await asyncio.gather(worker("a"), worker("b"))
    assert len(set(paths)) == 2
    assert Path.cwd() == original
    assert worktree_path.get() is None


def test_explore_rejects_unclassified_write_tool():
    def write_file(path: str):
        Path(path).write_text("mutated")

    with pytest.raises(PermissionError):
        create_agent("Generator", agent_type="Explore", tools=[write_file])


def test_schema_content_changes_cache_key():
    from pydantic import create_model

    def key(schema):
        return agent_cache_key(
            "same",
            schema=schema,
            tools=None,
            instructions="",
            label=None,
            phase=None,
            model="test",
            isolation=None,
            agent_type=None,
        )

    assert key(create_model("Answer", value=(int, ...))) != key(
        create_model("Answer", value=(str, ...))
    )


@pytest.mark.parametrize("wrapped", [False, True])
def test_explore_only_reaches_declared_reads(wrapped):
    from google.adk.tools import FunctionTool

    from dialectica.tool_policy import tool_capability

    @tool_capability(access="read", version="1")
    def read_file() -> str:
        return "evidence"

    @tool_capability(access="write", version="1")
    def write_file() -> str:
        raise AssertionError("must not execute")

    read = FunctionTool(read_file) if wrapped else read_file
    write = FunctionTool(write_file) if wrapped else write_file
    assert create_agent("Generator", agent_type="Explore", tools=[read]).tools == [read]
    with pytest.raises(PermissionError):
        create_agent("Generator", agent_type="Explore", tools=[read, write])


async def test_batch_failure_has_successes_and_error_evidence(tmp_path):
    from dialectica import workflow as wf

    async def ok():
        return "kept"

    async def bad():
        raise ValueError("concrete failure")

    async def script():
        return await wf.parallel([ok, bad])

    run = wf.Workflow(script, journal_dir=tmp_path)
    with pytest.raises(wf.BatchFailed) as caught:
        await run.run()
    assert caught.value.outcomes[0].value == "kept"
    assert caught.value.outcomes[1].error_type == "ValueError"
    assert "concrete failure" in caught.value.outcomes[1].traceback
    assert run.report.status == "failed"


@pytest.mark.parametrize("mode", ["collect", "legacy"])
async def test_pipeline_partial_never_reports_complete(tmp_path, mode):
    from dialectica import workflow as wf

    async def first(prev, item, index):
        return item * 2

    async def second(prev, item, index):
        if index:
            raise RuntimeError("stage two")
        return prev + 1

    async def script():
        return await wf.pipeline([1, 2], first, second, errors=mode)

    run = wf.Workflow(script, journal_dir=tmp_path)
    values = await run.run()
    assert run.report.status == "partial"
    failure = run.report.outcomes[1]
    assert failure.completed_stages == 1
    assert failure.value == 4
    assert values[0] == (3 if mode == "legacy" else run.report.outcomes[0])


async def test_token_gate_rechecks_queued_work(tmp_path, monkeypatch):
    from dialectica import workflow as wf
    from dialectica.agent_runtime import AgentResponse, TokenUsage

    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        await asyncio.sleep(0)
        return AgentResponse("ok", TokenUsage(output_tokens=10, model_calls=1))

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)

    async def script():
        return await wf.parallel(
            [lambda: wf.agent("one"), lambda: wf.agent("two")], errors="collect"
        )

    run = wf.Workflow(
        script,
        journal_dir=tmp_path,
        concurrency=1,
        budget_unit="tokens",
        budget_total=10,
    )
    outcomes = await run.run()
    assert calls == ["one"]
    assert outcomes[1].error_type == "BudgetExhausted"
    assert run.report.usage.model_calls == 1


async def test_unknown_usage_blocks_more_token_budget_work(tmp_path, monkeypatch):
    from dialectica import workflow as wf

    async def fake(agent, instruction):
        return "unknown usage"

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)

    async def script():
        await wf.agent("one")
        await wf.agent("two")

    run = wf.Workflow(
        script, journal_dir=tmp_path, budget_unit="tokens", budget_total=100
    )
    with pytest.raises(wf.BudgetExhausted, match="unknown usage"):
        await run.run()
    assert run.report.usage.unknown_calls == 1
    assert run.report.usage.model_calls == 0  # fake exposes no actual turns


async def test_verifier_indeterminate_stops_repairs_with_evidence(
    tmp_path, monkeypatch
):
    from dialectica import workflow as wf
    from dialectica.repair import VerificationResult, create_repair_engine

    calls = []

    async def fake(agent, instruction):
        calls.append(instruction)
        return "candidate"

    async def verifier(answer):
        return VerificationResult(
            "indeterminate", "test runner unavailable", "exit=127"
        )

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    engine = create_repair_engine("fix", verifier, max_attempts=3)

    async def script():
        return await engine.run()

    result = await wf.Workflow(script, journal_dir=tmp_path).run()
    assert result["passed"] is False
    assert result["status"] == "indeterminate"
    assert result["history"][0]["evidence"] == "exit=127"
    assert len(calls) == 1


def test_verifier_rejects_truthy_non_boolean():
    from dialectica.repair import verify

    result = asyncio.run(verify(lambda answer: ("yes", "weak"), "candidate"))
    assert result.status == "indeterminate"


async def test_verified_tool_reuse_and_refusal_of_unverified_effects(
    tmp_path, monkeypatch
):
    from dialectica import workflow as wf
    from dialectica.tool_policy import tool_capability

    calls = []
    artifact = tmp_path / "artifact"
    holder = {}

    @tool_capability(access="write", version="1")
    def write_artifact() -> str:
        artifact.write_text("done")
        return "done"

    async def fake(agent, instruction):
        calls.append(instruction)
        return write_artifact()

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent(
            "write",
            tools=[write_artifact],
            replay_version="artifact-v1",
            verify_cached=lambda result: (
                artifact.exists() and artifact.read_text() == result
            ),
        )

    await wf.Workflow(script, journal_dir=tmp_path, resume_version="1").run()
    await wf.Workflow(
        script, journal_dir=tmp_path, resume_version="1", resume_run_id=holder["id"]
    ).run()
    assert calls == ["write"]
    artifact.write_text("changed externally")
    with pytest.raises(wf.ResumeUnsafeError):
        await wf.Workflow(
            script, journal_dir=tmp_path, resume_version="1", resume_run_id=holder["id"]
        ).run()
    assert calls == ["write"]


async def test_no_resume_contract_recomputes_pure_steps(tmp_path, monkeypatch):
    from dialectica import workflow as wf

    calls, holder = [], {}

    async def fake(agent, instruction):
        calls.append(instruction)
        return "ok"

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("one")

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    await wf.Workflow(script, journal_dir=tmp_path).run()
    await wf.Workflow(script, journal_dir=tmp_path, resume_run_id=holder["id"]).run()
    assert calls == ["one", "one"]


def test_process_death_reuses_prefix_and_blocks_uncertain_effect(tmp_path):
    import os
    import sys

    script = tmp_path / "crash_case.py"
    script.write_text("""
import asyncio
import os
from pathlib import Path
from dialectica import workflow as wf
from dialectica.tool_policy import tool_capability
root = Path(os.environ["CASE_ROOT"])
effect = os.environ["EFFECT"] == "1"
@tool_capability(access="write", version="1")
def write_effect() -> str:
    with (root / "effects").open("a") as stream:
        stream.write("effect\\n")
    return "done"
async def fake(agent, instruction):
    with (root / "calls").open("a") as stream:
        stream.write(instruction + "\\n")
    if instruction == "second" and os.environ["CRASH"] == "1":
        if effect:
            write_effect()
        os._exit(17)
    return "ok"
async def script():
    (root / "id").write_text(wf.run_id())
    await wf.agent("first")
    return await wf.agent("second", tools=[write_effect] if effect else None)
wf.agent_runtime.run_agent = fake
wf.get_model_config = lambda role: "offline"
resume = (root / "id").read_text() if (root / "id").exists() else None
try:
    asyncio.run(wf.Workflow(script, args={"effect": effect}, resume_version="1",
                           journal_dir=root / "journals", resume_run_id=resume).run())
except wf.ResumeUnsafeError:
    raise SystemExit(23)
""")
    for effect in (False, True):
        root = tmp_path / str(effect)
        root.mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "CASE_ROOT": str(root),
            "EFFECT": "1" if effect else "0",
            "CRASH": "1",
        }
        first = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert first.returncode == 17, first.stderr
        env["CRASH"] = "0"
        second = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert second.returncode == (23 if effect else 0), second.stderr
        assert (root / "calls").read_text().splitlines() == (
            ["first", "second"] if effect else ["first", "second", "second"]
        )
        if effect:
            assert (root / "effects").read_text() == "effect\n"


def test_tool_fingerprint_is_stable_across_processes_and_changes_with_source(tmp_path):
    import os
    import sys

    script = tmp_path / "key.py"
    source = """
from dialectica.tool_policy import tool_capability
from dialectica.workflow_journal import agent_cache_key
@tool_capability(access="read", version="1")
def read() -> str:
    return "VERSION"
print(agent_cache_key("p", schema=None, tools=[read], instructions="", label=None,
                      phase=None, model="fixed", isolation=None, agent_type="Explore"))
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    def key(version):
        script.write_text(source.replace("VERSION", version))
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip()

    assert key("1") == key("1")
    assert key("1") != key("2")


async def test_shared_model_turn_limit_stops_real_adk_tool_loop(tmp_path, monkeypatch):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from dialectica import workflow as wf
    from dialectica.agent_runtime import ModelTurnLimitExceeded

    class ToolLoop(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_function_call(name="read", args={})],
                ),
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    total_token_count=3
                ),
            )

    def read() -> str:
        return "observed"

    model = ToolLoop(model="offline")
    monkeypatch.setattr(wf, "get_model_config", lambda role: model)

    async def script():
        await wf.agent("loop", tools=[read])

    run = wf.Workflow(script, journal_dir=tmp_path, model_turn_limit=2)
    with pytest.raises(ModelTurnLimitExceeded):
        await run.run()
    assert run.report.usage.model_calls == 2
    assert run.report.usage.total_tokens == 6


async def test_async_cached_verifiers_reserve_distinct_parallel_positions(
    tmp_path, monkeypatch
):
    from dialectica import workflow as wf

    holder, calls = {}, []

    async def fake(agent, instruction):
        calls.append(instruction)
        return instruction

    async def verify(result):
        await asyncio.sleep(0.001)
        return result in ("first", "second")

    async def script():
        holder["id"] = wf.run_id()
        return await wf.parallel(
            [
                lambda: wf.agent("first", replay_version="v1", verify_cached=verify),
                lambda: wf.agent("second", replay_version="v1", verify_cached=verify),
            ]
        )

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    assert await wf.Workflow(
        script, journal_dir=tmp_path, resume_version="v1"
    ).run() == ["first", "second"]
    calls.clear()
    assert await wf.Workflow(
        script, journal_dir=tmp_path, resume_version="v1", resume_run_id=holder["id"]
    ).run() == ["first", "second"]
    assert calls == []


async def test_active_run_cannot_be_resumed_concurrently(tmp_path, monkeypatch):
    from dialectica import workflow as wf
    from dialectica.workflow_journal import JournalBusyError

    entered, release = asyncio.Event(), asyncio.Event()
    holder = {}

    async def fake(agent, instruction):
        entered.set()
        await release.wait()
        return "done"

    async def script():
        holder["id"] = wf.run_id()
        return await wf.agent("one")

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    active = asyncio.create_task(wf.Workflow(script, journal_dir=tmp_path).run())
    await entered.wait()
    try:
        with pytest.raises(JournalBusyError):
            await wf.Workflow(
                script, journal_dir=tmp_path, resume_run_id=holder["id"]
            ).run()
    finally:
        release.set()
        await active


@pytest.mark.parametrize(
    "content", ['{"contract_version": 2,', "{}", '{"contract_version": 1}']
)
def test_damaged_or_legacy_journal_is_refused(tmp_path, content):
    from dialectica.workflow_journal import RunJournal

    root = tmp_path / "run"
    root.mkdir()
    (root / "journal.jsonl").write_text(content)
    with pytest.raises(ValueError):
        RunJournal.load("run", tmp_path)


async def test_repair_abort_retains_completed_verifier_history(tmp_path, monkeypatch):
    from dialectica import workflow as wf
    from dialectica.repair import VerificationResult, create_repair_engine

    async def fake(agent, instruction):
        return "broken"

    engine = create_repair_engine(
        "fix", lambda answer: VerificationResult("fail", "assert failed", "exit 1")
    )

    async def script():
        return await engine.run()

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    with pytest.raises(wf.BudgetExhausted):
        await wf.Workflow(script, journal_dir=tmp_path, budget_total=1).run()
    assert engine.last_history == [
        {
            "attempt": 1,
            "passed": False,
            "model": "default",
            "status": "fail",
            "feedback": "assert failed",
            "evidence": "exit 1",
        }
    ]


def test_non_json_inputs_do_not_alias_json_cache_keys():
    from dialectica.workflow_journal import args_fingerprint

    assert args_fingerprint({"x": [1]}) == args_fingerprint({"x": [1]})
    assert args_fingerprint((1,)) != args_fingerprint([1])
    assert args_fingerprint({1: "value"}) != args_fingerprint({"1": "value"})
    assert args_fingerprint(object()) != args_fingerprint(object())


@pytest.mark.parametrize("workers", [False, True])
async def test_worktree_path_reaches_real_concurrent_adk_tools(
    git_repo, monkeypatch, tmp_path, workers
):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from dialectica import workflow as wf

    monkeypatch.chdir(git_repo)
    if workers:
        monkeypatch.setenv("DIALECTICA_TOOL_WORKERS", "2")
    else:
        monkeypatch.delenv("DIALECTICA_TOOL_WORKERS", raising=False)
    paths = []

    class WorktreeModel(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            has_result = any(
                part.function_response
                for content in llm_request.contents
                for part in content.parts or []
            )
            part = (
                types.Part.from_text(text="done")
                if has_result
                else types.Part.from_function_call(name="write_marker", args={})
            )
            yield LlmResponse(content=types.Content(role="model", parts=[part]))

    def write_marker() -> str:
        path = wf.worktree_path.get()
        assert path is not None
        paths.append(path)
        (path / "marker").write_text("local edit")
        return "written"

    monkeypatch.setattr(
        wf, "get_model_config", lambda role: WorktreeModel(model="offline")
    )

    async def script():
        return await wf.parallel(
            [
                lambda: wf.agent("first", tools=[write_marker], isolation="worktree"),
                lambda: wf.agent("second", tools=[write_marker], isolation="worktree"),
            ]
        )

    try:
        assert await wf.Workflow(script, journal_dir=tmp_path / "journals").run() == [
            "done",
            "done",
        ]
        assert len(set(paths)) == 2
        assert Path.cwd() == git_repo
        for path in paths:
            assert (path / "marker").read_text() == "local edit"
        assert not (git_repo / "marker").exists()
    finally:
        for path in paths:
            await asyncio.to_thread(
                subprocess.run,
                [
                    "git",
                    "-C",
                    str(git_repo),
                    "worktree",
                    "remove",
                    str(path),
                    "--force",
                ],
                check=True,
                capture_output=True,
            )


async def test_rejected_cached_verification_invalidates_tail(tmp_path, monkeypatch):
    from dialectica import workflow as wf

    holder, calls = {}, []
    accept = True

    async def fake(agent, instruction):
        calls.append(instruction)
        return "ok"

    async def script():
        holder["id"] = wf.run_id()
        await wf.agent(
            "first", replay_version="v1", verify_cached=lambda result: accept
        )
        return await wf.agent("tail")

    monkeypatch.setattr(wf.agent_runtime, "run_agent", fake)
    await wf.Workflow(script, journal_dir=tmp_path, resume_version="v1").run()
    calls.clear()
    accept = False
    await wf.Workflow(
        script, journal_dir=tmp_path, resume_version="v1", resume_run_id=holder["id"]
    ).run()
    assert calls == ["first", "tail"]


@pytest.mark.parametrize("primitive", ["parallel", "pipeline"])
async def test_child_cancellation_settles_siblings_before_run_finishes(
    tmp_path, primitive
):
    from dialectica import workflow as wf

    started, cancelled = asyncio.Event(), asyncio.Event()

    async def sibling():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def stop():
        await started.wait()
        raise asyncio.CancelledError()

    async def stage(prev, item, index):
        return await (sibling() if index == 0 else stop())

    async def script():
        if primitive == "parallel":
            return await wf.parallel([sibling, stop])
        return await wf.pipeline([0, 1], stage)

    run = wf.Workflow(script, journal_dir=tmp_path)
    with pytest.raises(asyncio.CancelledError):
        await run.run()
    assert cancelled.is_set()
    assert run.report.status == "cancelled"
