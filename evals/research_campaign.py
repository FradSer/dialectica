"""Frozen repeated held-out campaign; all studies declared before first dispatch.

No adaptive tuning or automatic restart. Individual model failures remain arm
outcomes; a harness/analysis failure terminates the campaign with saved state.
The source snapshot permits later reproduction of local implementation, but
cannot freeze an opaque provider's model routing or billing.
"""

import argparse
import asyncio
import hashlib
import json
import random
import subprocess
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path

from evals import claim_ablation, evidence_ablation, meta_ablation
from evals.evidence_tasks import make_evidence_tasks
from evals.experiment_protocol import ROOT, digest, freeze_protocol
from evals.research_tasks import make_portfolio_tasks, make_state_tasks

SMALL = "openai:gemini-3.5-flash-lite"
STRONG = "openai:gpt-5.5"
OTHER = "openai:qwen3.8-flash"


def default_studies() -> list[dict]:
    """Predetermined budgets/controls from development, not held-out outcomes."""
    studies = []
    for allowance in (6, 12):
        studies.append(
            {
                "name": f"meta-gemini-budget{allowance}",
                "kind": "meta",
                "parameters": {
                    "models": [SMALL],
                    "split": "heldout",
                    "count": 8,
                    "family": "portfolio",
                    "difficulty": 8,
                    "allowance": allowance,
                    "repeats": 3,
                    "arms": list(meta_ablation.ARMS),
                    "order_seed": 10430,
                },
            }
        )
    for samples in (3, 6):
        studies.append(
            {
                "name": f"claims-gemini-k{samples}",
                "kind": "claim",
                "parameters": {
                    "models": [SMALL],
                    "split": "heldout",
                    "count": 8,
                    "size": 8,
                    "samples": samples,
                    "repeats": 3,
                    "arms": list(claim_ablation.ARMS),
                    "order_seed": 10431,
                },
            }
        )
    studies.extend(
        [
            {
                "name": "strong-meta-single",
                "kind": "meta",
                "parameters": {
                    "models": [STRONG],
                    "split": "heldout",
                    "count": 8,
                    "family": "portfolio",
                    "difficulty": 8,
                    "allowance": 1,
                    "repeats": 3,
                    "arms": ["single"],
                    "order_seed": 10430,
                },
            },
            {
                "name": "strong-claim-single",
                "kind": "claim",
                "parameters": {
                    "models": [STRONG],
                    "split": "heldout",
                    "count": 8,
                    "size": 8,
                    "samples": 1,
                    "repeats": 3,
                    "arms": ["single"],
                    "order_seed": 10431,
                },
            },
            {
                "name": "evidence-roster-budget12",
                "kind": "evidence",
                "parameters": {
                    "models": [SMALL, OTHER, STRONG],
                    "judges": [SMALL, OTHER],
                    "judge_families": ["gemini", "qwen"],
                    "split": "heldout",
                    "count": 6,
                    "allowance": 12,
                    "repeats": 2,
                    "arms": list(evidence_ablation.ARMS),
                    "order_seed": 10427,
                },
            },
        ]
    )
    return studies


def task_pool(studies: list[dict]) -> list:
    tasks = {}
    names = set()
    for study in studies:
        name = study["name"]
        if (
            not name
            or any(not (char.isalnum() or char in "-_") for char in name)
            or name in names
        ):
            raise ValueError("unique safe study names required")
        names.add(name)
        params = study["parameters"]
        if params["split"] != "heldout":
            raise ValueError("campaign studies must use the predeclared held-out split")
        if study["kind"] == "evidence":
            generated = make_evidence_tasks(params["split"], params["count"])
        elif study["kind"] == "claim":
            generated = make_portfolio_tasks(
                params["split"], params["count"], params["size"]
            )
        elif study["kind"] == "meta":
            if params["family"] == "portfolio":
                generated = make_portfolio_tasks(
                    params["split"], params["count"], params["difficulty"]
                )
            elif params["family"] == "state":
                generated = make_state_tasks(
                    params["split"], params["count"], params["difficulty"]
                )
            else:
                raise ValueError("unknown objective task family")
        else:
            raise ValueError("unknown study kind")
        for task in generated:
            if (
                task.task_id in tasks
                and tasks[task.task_id].statement != task.statement
            ):
                raise ValueError("same task ID cannot refer to different questions")
            tasks[task.task_id] = task
    return list(tasks.values())


def source_fingerprints() -> dict[str, str]:
    sources = sorted(
        path
        for directory in ("dialectica", "evals", "examples/patterns")
        for path in (ROOT / directory).rglob("*.py")
    ) + [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }


def verify_campaign(output: Path, report: dict) -> dict:
    """Bind every study to the initial campaign source archive and configuration."""
    protocol = json.loads((output / "campaign.protocol.json").read_text())
    if digest(protocol) != report["predeclaration_digest"]:
        raise ValueError("campaign protocol fingerprint mismatch")
    if any(
        report.get(key) != value for key, value in protocol["configuration"].items()
    ):
        raise ValueError("campaign configuration differs from initial declaration")
    archive_path = output / "sources.zip"
    if (
        hashlib.sha256(archive_path.read_bytes()).hexdigest()
        != report["source_archive_sha256"]
    ):
        raise ValueError("campaign source snapshot changed")
    if any(
        version(name) != expected for name, expected in protocol["dependencies"].items()
    ):
        raise ValueError("campaign dependency version changed")
    expected = protocol["source_digests"]
    if source_fingerprints() != expected:
        raise ValueError("campaign source differs from initial snapshot")
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != set(expected) or len(archive.namelist()) != len(
            expected
        ):
            raise ValueError("campaign source snapshot membership differs")
        for name, fingerprint in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != fingerprint:
                raise ValueError("campaign source snapshot fingerprint mismatch")
    return protocol


def verify_child(output: Path, row: dict, study: dict, campaign: dict) -> dict:
    protocol_path = (output / row["output"]).with_suffix(".protocol.json")
    protocol = json.loads(protocol_path.read_text())
    if (
        protocol["source_digests"] != campaign["source_digests"]
        or protocol["dependencies"] != campaign["dependencies"]
    ):
        raise ValueError("study implementation differs from frozen campaign")
    catalog = {task["task_id"]: task["statement"] for task in campaign["tasks"]}
    expected_tasks = {task.task_id: task.statement for task in task_pool([study])}
    actual_tasks = {task["task_id"]: task["statement"] for task in protocol["tasks"]}
    if actual_tasks != expected_tasks or len(actual_tasks) != len(protocol["tasks"]):
        raise ValueError("study task pool differs from frozen campaign")
    if any(
        catalog.get(task["task_id"]) != task["statement"] for task in protocol["tasks"]
    ):
        raise ValueError("study task differs from frozen campaign")
    for key, value in study["parameters"].items():
        target = key
        if study["kind"] == "evidence":
            target = {
                "arms": "requested_arms",
                "judge_families": "judge_families_declared",
            }.get(key, key)
        if protocol["configuration"].get(target) != value:
            raise ValueError("study configuration differs from frozen campaign")
    return protocol


def archive_sources(output: Path) -> str:
    """Save only Python source and dependency manifests, excluding environment files."""
    sources = sorted(
        path
        for directory in ("dialectica", "evals", "examples/patterns")
        for path in (ROOT / directory).rglob("*.py")
    ) + [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sources:
            archive.write(path, str(path.relative_to(ROOT)))
    return hashlib.sha256(output.read_bytes()).hexdigest()


async def run(output: Path, *, studies: list[dict] | None = None) -> dict:
    """Freeze all study parameters/source bytes, execute once, save terminal states."""
    output = output.resolve()
    studies = json.loads(json.dumps(default_studies() if studies is None else studies))
    tasks = task_pool(studies)
    path = output / "campaign.json"
    if path.exists() or path.with_suffix(".protocol.json").exists():
        raise FileExistsError(f"campaign already exists: {path}")
    for study in studies:
        for suffix in (".json", ".protocol.json", ".analysis.json", ".terminal.json"):
            target = output / (study["name"] + suffix)
            if target.exists():
                raise FileExistsError(f"study artifact already exists: {target}")
    output.mkdir(parents=True, exist_ok=True)
    archive_hash = archive_sources(output / "sources.zip")
    order = [study["name"] for study in studies]
    random.Random(10432).shuffle(order)
    report = {
        "protocol": "research-campaign-v1",
        "studies": studies,
        "study_order_seed": 10432,
        "study_order": order,
        "source_archive": "sources.zip",
        "source_archive_sha256": archive_hash,
        "inference_scope": "exploratory repeated held-out comparisons; no universal superiority claim",
        "cost_scope": "reported tokens and observable ADK turns; no token/dollar parity",
        "judge_limit": "calibration tests obvious factual violations; generator/judge family overlap may bias preferences",
        "rows": [],
    }
    freeze_protocol(path, report, tasks)
    by_name = {study["name"]: study for study in studies}
    runners = {
        "meta": meta_ablation.run,
        "claim": claim_ablation.run,
        "evidence": evidence_ablation.run,
    }

    def save() -> None:
        path.write_text(json.dumps(report, indent=2))

    for name in order:
        study = by_name[name]
        row = {
            "study": name,
            "status": "running",
            "phase": "generation",
            "output": f"{name}.json",
        }
        report["rows"].append(row)
        save()
        try:
            campaign_protocol = verify_campaign(output, report)
            params = dict(study["parameters"])
            if "arms" in params:
                params["arms"] = tuple(params["arms"])
            await runners[study["kind"]](output / row["output"], **params)
            row["phase"] = "analysis"
            save()
            verify_campaign(output, report)
            child_protocol = verify_child(output, row, study, campaign_protocol)
            analysis_module = (
                "evals.evidence_analysis"
                if study["kind"] == "evidence"
                else "evals.objective_analysis"
            )
            analysis = output / f"{name}.analysis.json"
            await asyncio.to_thread(
                subprocess.run,
                [
                    sys.executable,
                    "-m",
                    analysis_module,
                    str(output / row["output"]),
                    "--output",
                    str(analysis),
                ],
                check=True,
                cwd=ROOT,
            )
            row["analysis"] = analysis.name
            analyzed = json.loads(analysis.read_text())
            row["analysis_status"] = analyzed["predeclaration_status"]
            expected_bindings = {
                "input_report_digest": hashlib.sha256(
                    (output / row["output"]).read_bytes()
                ).hexdigest(),
                "input_protocol_digest": hashlib.sha256(
                    (output / row["output"]).with_suffix(".protocol.json").read_bytes()
                ).hexdigest(),
                "input_task_digest": child_protocol["task_digest"],
                "input_configuration_digest": child_protocol["configuration_digest"],
            }
            expected_schema = child_protocol["analysis_rules"][
                "evidence" if study["kind"] == "evidence" else "objective"
            ]["method"]
            if (
                analyzed.get("schema") != expected_schema
                or row["analysis_status"] != "verified"
                or any(
                    analyzed.get(key) != value
                    for key, value in expected_bindings.items()
                )
            ):
                raise ValueError(
                    "campaign requires analysis bound to this verified study"
                )
            verify_campaign(output, report)
            terminal = {
                "status": "complete",
                "phase": "analysis",
                "report": row["output"],
                **expected_bindings,
                "analysis_digest": hashlib.sha256(analysis.read_bytes()).hexdigest(),
                "source_archive_sha256": report["source_archive_sha256"],
            }
            with (output / f"{name}.terminal.json").open("x") as stream:
                stream.write(json.dumps(terminal, indent=2))
            row["terminal"] = f"{name}.terminal.json"
            row["status"] = "complete"
        except BaseException as error:
            status = (
                "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
            )
            row.update(status=status, error=type(error).__name__)
            terminal = {
                "status": status,
                "phase": row["phase"],
                "error": type(error).__name__,
                "report": row["output"],
                "campaign": "campaign.json",
            }
            with (output / f"{name}.terminal.json").open("x") as stream:
                stream.write(json.dumps(terminal, indent=2))
            row["terminal"] = f"{name}.terminal.json"
            save()
            raise
        save()
        print(json.dumps({"study": name, "status": row["status"]}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
