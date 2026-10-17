"""Executable fixture provenance and real failed-test -> patch -> test evidence."""

import json
from types import SimpleNamespace

import pytest

from evals.workflow_bug_fixtures import FIXTURES
from evals.workflow_bugfix_eval import prepare, run_arm


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.id)
def test_every_authored_fixture_has_a_real_failure_and_small_passing_fix(
    tmp_path, fixture
):
    host = prepare(tmp_path / fixture.id, fixture)
    assert "not a historical" in fixture.provenance
    assert host.verify().status == "fail"
    host.tools[1](fixture.fixed)
    assert host.verify().status == "pass"
    assert "--- a/target.py" in host.diff()
    assert host.test_runs[0]["exit_code"] != 0
    assert host.test_runs[-1]["exit_code"] == 0


def test_host_rejects_modified_tests_and_outside_paths(tmp_path):
    host = prepare(tmp_path / "case", FIXTURES[0])
    with pytest.raises(PermissionError):
        host.tools[0]("../target.py")
    (host.root / "test_target.py").write_text("# tampered")
    assert host.verify().status == "indeterminate"


@pytest.mark.parametrize("arm", ["single", "workflow"])
async def test_offline_pair_records_unknown_cost_and_artifacts(tmp_path, arm):
    config = SimpleNamespace(
        model="google:offline-smoke",
        model_version="smoke-v1",
        live=False,
        turn_limit=12,
        timeout=30,
    )
    root = tmp_path / arm
    result = await run_arm(root, FIXTURES[0], arm, config)
    assert result["completed"]
    assert result["mode"] == "offline_smoke"
    assert result["usage"] is None
    assert result["cost_usd"] is None
    assert (root / "patch.diff").read_text()
    tests = json.loads((root / "tests.json").read_text())
    assert tests[0]["exit_code"] != 0
    assert tests[-1]["exit_code"] == 0
