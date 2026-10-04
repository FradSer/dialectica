"""Predeclaration preserves evidence and fingerprints inputs without secrets."""

import json

import pytest

from evals.experiment_protocol import digest, freeze_protocol
from evals.research_tasks import make_state_tasks


def test_protocol_fingerprints_configuration_tasks_sources_and_safe_runtime(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-must-not-be-recorded")
    monkeypatch.setenv("CLIPROXYAPI_TOKEN", "another-private-token")
    monkeypatch.setenv("DIALECTICA_DISABLE_THINKING", "true")
    output = tmp_path / "result.json"
    report = {"split": "heldout", "models": ["google:test"], "rows": []}
    freeze_protocol(output, report, make_state_tasks("heldout", 2, steps=3))
    raw = output.with_suffix(".protocol.json").read_text()
    protocol = json.loads(raw)
    assert "secret-must-not-be-recorded" not in raw
    assert "another-private-token" not in raw
    assert protocol["runtime_flags"]["DIALECTICA_DISABLE_THINKING"] == "true"
    assert protocol["task_digest"] == digest(protocol["tasks"])
    assert protocol["configuration_digest"] == digest(protocol["configuration"])
    assert report["predeclaration_digest"] == digest(protocol)
    assert protocol["source_digests"]["uv.lock"]
    assert protocol["dependencies"]["google-adk"]
    assert len(protocol["tasks"]) == 2
    saved = output.with_suffix(".protocol.json").read_bytes()
    output.unlink()
    with pytest.raises(FileExistsError):
        freeze_protocol(output, report, make_state_tasks("dev", 1, steps=3))
    assert output.with_suffix(".protocol.json").read_bytes() == saved
    assert not output.exists()


def test_duplicate_task_ids_fail_before_creating_experiment(tmp_path):
    task = make_state_tasks("dev", 1, steps=2)[0]
    output = tmp_path / "duplicate.json"
    with pytest.raises(ValueError, match="task"):
        freeze_protocol(output, {"rows": []}, [task, task])
    assert not output.exists()
    assert not output.with_suffix(".protocol.json").exists()
