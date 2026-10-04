"""Freeze the whole campaign and preserve source bytes before dispatch."""

import hashlib
import json
import subprocess
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from evals.experiment_protocol import freeze_protocol, load_frozen_report
from evals.research_campaign import run, task_pool


def save_frozen_child(output, kwargs):
    params = json.loads(json.dumps(kwargs))
    study = {"name": "probe", "kind": "meta", "parameters": params}
    freeze_protocol(output, {**params, "rows": []}, task_pool([study]))


async def test_campaign_freezes_every_study_and_sources_before_dispatch(tmp_path):
    studies = [
        {
            "name": "probe",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 1,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
                "order_seed": 10432,
            },
        }
    ]

    async def dispatch(output, **kwargs):
        protocol = json.loads((tmp_path / "campaign.protocol.json").read_text())
        assert protocol["configuration"]["studies"] == studies
        archive = tmp_path / "sources.zip"
        assert (
            hashlib.sha256(archive.read_bytes()).hexdigest()
            == protocol["configuration"]["source_archive_sha256"]
        )
        with zipfile.ZipFile(archive) as source:
            for name, expected in protocol["source_digests"].items():
                assert hashlib.sha256(source.read(name)).hexdigest() == expected
        assert kwargs["split"] == "heldout"
        save_frozen_child(output, kwargs)
        return {"rows": []}

    def analysis(command, **kwargs):
        assert kwargs["check"] is True
        from pathlib import Path

        _, _, metadata = load_frozen_report(
            Path(command[-3]),
            rule_family="objective",
            analysis_source="evals/objective_analysis.py",
        )
        Path(command[-1]).write_text(
            json.dumps({"schema": "objective-analysis-v1", **metadata})
        )
        return subprocess.CompletedProcess(command, 0)

    with (
        patch(
            "evals.research_campaign.meta_ablation.run", AsyncMock(side_effect=dispatch)
        ) as calls,
        patch("evals.research_campaign.subprocess.run", side_effect=analysis),
    ):
        report = await run(tmp_path, studies=studies)
        assert report["rows"][0]["status"] == "complete"
        assert report["rows"][0]["analysis_status"] == "verified"
        assert calls.await_count == 1
        with pytest.raises(FileExistsError):
            await run(tmp_path, studies=studies)
        assert calls.await_count == 1


async def test_failed_campaign_preserves_terminal_state_and_stops(tmp_path):
    studies = [
        {
            "name": "first",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 1,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
            },
        }
    ]
    with (
        patch(
            "evals.research_campaign.meta_ablation.run",
            AsyncMock(side_effect=ValueError("bad protocol")),
        ),
        pytest.raises(ValueError),
    ):
        await run(tmp_path, studies=studies)
    report = json.loads((tmp_path / "campaign.json").read_text())
    assert report["rows"][0]["status"] == "failed"
    assert report["rows"][0]["error"] == "ValueError"


async def test_snapshot_replacement_and_unrelated_verified_analysis_stop_campaign(
    tmp_path,
):
    from pathlib import Path

    studies = [
        {
            "name": "probe",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 1,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
            },
        }
    ]

    async def dispatch(output, **kwargs):
        save_frozen_child(output, kwargs)
        return {"rows": []}

    def wrong_analysis(command, **kwargs):
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "predeclaration_status": "verified",
                    "input_report_digest": "unrelated",
                }
            )
        )
        return subprocess.CompletedProcess(command, 0)

    with (
        patch(
            "evals.research_campaign.meta_ablation.run", AsyncMock(side_effect=dispatch)
        ),
        patch("evals.research_campaign.subprocess.run", side_effect=wrong_analysis),
        pytest.raises(ValueError, match="bound"),
    ):
        await run(tmp_path / "wrong-analysis", studies=studies)

    async def replace_snapshot(output, **kwargs):
        save_frozen_child(output, kwargs)
        with (output.parent / "sources.zip").open("ab") as archive:
            archive.write(b"changed")
        return {"rows": []}

    with (
        patch(
            "evals.research_campaign.meta_ablation.run",
            AsyncMock(side_effect=replace_snapshot),
        ),
        patch(
            "evals.research_campaign.subprocess.run", side_effect=wrong_analysis
        ) as analysis,
    ):
        with pytest.raises(ValueError, match="snapshot"):
            await run(tmp_path / "changed-snapshot", studies=studies)
        analysis.assert_not_called()


async def test_cancelled_child_has_a_standalone_terminal_receipt(tmp_path):
    import asyncio

    from evals.experiment_protocol import freeze_protocol
    from evals.research_campaign import task_pool

    studies = [
        {
            "name": "probe",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 1,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
            },
        }
    ]
    started = asyncio.Event()

    async def pending(output, **kwargs):
        freeze_protocol(output, {"rows": []}, task_pool(studies))
        started.set()
        await asyncio.Future()

    with patch(
        "evals.research_campaign.meta_ablation.run", AsyncMock(side_effect=pending)
    ):
        task = asyncio.create_task(run(tmp_path, studies=studies))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    terminal = json.loads((tmp_path / "probe.terminal.json").read_text())
    assert terminal["status"] == "cancelled"
    assert terminal["phase"] == "generation"
    assert json.loads((tmp_path / "probe.json").read_text())["rows"] == []


async def test_source_drift_after_generation_blocks_analysis(tmp_path):
    from evals.research_campaign import source_fingerprints

    studies = [
        {
            "name": "probe",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 1,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
            },
        }
    ]
    changed = False

    def fingerprints():
        result = source_fingerprints()
        if changed:
            result["evals/claim_ablation.py"] = "changed"
        return result

    async def dispatch(output, **kwargs):
        nonlocal changed
        save_frozen_child(output, kwargs)
        changed = True
        return {"rows": []}

    with (
        patch(
            "evals.research_campaign.meta_ablation.run", AsyncMock(side_effect=dispatch)
        ),
        patch("evals.research_campaign.source_fingerprints", side_effect=fingerprints),
        patch("evals.research_campaign.subprocess.run") as analysis,
        pytest.raises(ValueError, match="initial snapshot"),
    ):
        await run(tmp_path, studies=studies)
    analysis.assert_not_called()
    assert (
        json.loads((tmp_path / "probe.terminal.json").read_text())["status"] == "failed"
    )


async def test_child_cannot_shrink_predeclared_task_pool(tmp_path):
    studies = [
        {
            "name": "probe",
            "kind": "meta",
            "parameters": {
                "models": ["google:test"],
                "split": "heldout",
                "count": 2,
                "family": "portfolio",
                "difficulty": 4,
                "allowance": 1,
                "repeats": 1,
                "arms": ["single"],
            },
        }
    ]

    async def truncated(output, **kwargs):
        params = json.loads(json.dumps(kwargs))
        freeze_protocol(output, {**params, "rows": []}, task_pool(studies)[:1])
        return {"rows": []}

    def analysis(command, **kwargs):
        from pathlib import Path

        _, _, metadata = load_frozen_report(
            Path(command[-3]),
            rule_family="objective",
            analysis_source="evals/objective_analysis.py",
        )
        Path(command[-1]).write_text(
            json.dumps({"schema": "objective-analysis-v1", **metadata})
        )
        return subprocess.CompletedProcess(command, 0)

    with (
        patch(
            "evals.research_campaign.meta_ablation.run",
            AsyncMock(side_effect=truncated),
        ),
        patch("evals.research_campaign.subprocess.run", side_effect=analysis),
        pytest.raises(ValueError, match="task pool"),
    ):
        await run(tmp_path, studies=studies)
