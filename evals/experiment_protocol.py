"""Freeze experiment inputs before dispatch, without recording credentials.

This receipt establishes per-run predeclaration and prevents accidental reuse.
It is not external preregistration or proof that an analyst never saw held-out data.
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OBJECTIVE_ANALYSIS_RULES = {
    "method": "objective-analysis-v1",
    "baseline": "single",
    "bootstrap_unit": "task; repeats averaged within task",
    "draws": 2000,
    "seed": 10429,
    "interval": "95 percent percentile; exploratory, unadjusted",
    "failures": "incorrect system outcomes, retained in denominator",
    "unknown_usage": "cost incomplete, never interpreted as free",
    "degenerate_interval": "floor/ceiling cannot establish certainty",
}


EVIDENCE_ANALYSIS_RULES = {
    "method": "evidence-analysis-v1",
    "bootstrap_unit": "task; repeats averaged within task",
    "draws": 2000,
    "seed": 10433,
    "unknown_preferences": "bounded between minus one and plus one, never imputed ties",
    "validity": "both grounding gates and calibrated distinct recorded judge families",
    "disagreement": "inconclusive, not a tie or win",
    "baselines": "every declared roster model separately",
    "inference": "exploratory panel preference; no general or human quality superiority claim",
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def freeze_protocol(output: Path, report: dict, tasks: list) -> None:
    """Exclusively save protocol and initial report before any model invocation."""
    task_ids = [task.task_id for task in tasks]
    if not tasks or len(set(task_ids)) != len(task_ids):
        raise ValueError("nonempty tasks with unique task IDs required")
    protocol_path = output.with_suffix(".protocol.json")
    if output.exists() or protocol_path.exists():
        raise FileExistsError(f"experiment already exists: {output}")
    configuration = {
        key: value
        for key, value in report.items()
        if key not in {"rows", "calibration"}
    }
    sources = sorted(
        path
        for directory in ("dialectica", "evals", "examples/patterns")
        for path in (ROOT / directory).rglob("*.py")
    ) + [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    protocol = {
        "schema": "experiment-predeclaration-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "configuration": configuration,
        "tasks": [
            {"task_id": task.task_id, "statement": task.statement} for task in tasks
        ],
        "source_digests": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        "dependencies": {
            name: version(name) for name in ("google-adk", "litellm", "pydantic")
        },
        "runtime_flags": {
            name: os.environ.get(name)
            for name in (
                "DIALECTICA_DISABLE_THINKING",
                "DIALECTICA_CONTEXT_CACHE",
                "DIALECTICA_WORKFLOW_CONCURRENCY",
                "LITELLM_LOCAL_MODEL_COST_MAP",
            )
        },
        "analysis_rules": {
            "objective": OBJECTIVE_ANALYSIS_RULES,
            "evidence": EVIDENCE_ANALYSIS_RULES,
        },
        "limits": [
            "Workflow allowances do not enforce provider-request or dollar parity.",
            "Provider-internal routing and retries may remain opaque.",
            "Per-run freezing does not prevent tuning across separate experiments.",
        ],
    }
    protocol["task_digest"] = digest(protocol["tasks"])
    protocol["configuration_digest"] = digest(configuration)
    report["predeclaration_digest"] = digest(protocol)
    output.parent.mkdir(parents=True, exist_ok=True)
    with protocol_path.open("x") as stream:
        stream.write(json.dumps(protocol, indent=2, ensure_ascii=False))
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2))


def load_frozen_report(
    path: Path, *, rule_family: str, analysis_source: str, allow_drift: bool = False
) -> tuple[dict, list[str] | None, dict]:
    """Verify a frozen analysis contract, or explicitly record exploratory drift."""
    rules = {
        "objective": OBJECTIVE_ANALYSIS_RULES,
        "evidence": EVIDENCE_ANALYSIS_RULES,
    }[rule_family]
    report_bytes = path.read_bytes()
    report = json.loads(report_bytes)
    tasks = None
    metadata = {
        "predeclaration_status": "unregistered_analysis",
        "source_drift": {},
        "rule_drift": False,
    }
    metadata["input_report_digest"] = hashlib.sha256(report_bytes).hexdigest()
    metadata["input_protocol_digest"] = None
    metadata["input_task_digest"] = None
    metadata["input_configuration_digest"] = None
    if not report.get("predeclaration_digest"):
        return report, tasks, metadata
    protocol_bytes = path.with_suffix(".protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    metadata["input_protocol_digest"] = hashlib.sha256(protocol_bytes).hexdigest()
    metadata["input_task_digest"] = protocol["task_digest"]
    metadata["input_configuration_digest"] = protocol["configuration_digest"]
    if protocol["task_digest"] != digest(protocol["tasks"]) or protocol[
        "configuration_digest"
    ] != digest(protocol["configuration"]):
        raise ValueError("task/configuration fingerprint mismatch")
    if digest(protocol) != report["predeclaration_digest"]:
        raise ValueError("predeclaration fingerprint mismatch")
    if any(
        report.get(key) != value for key, value in protocol["configuration"].items()
    ):
        raise ValueError("report configuration differs from predeclaration")
    metadata["rule_drift"] = (
        protocol.get("analysis_rules", {}).get(rule_family) != rules
    )
    for relative, expected in protocol["source_digests"].items():
        source = ROOT / relative
        if not source.resolve().is_relative_to(ROOT):
            raise ValueError("source fingerprint path escapes repository")
        actual = (
            hashlib.sha256(source.read_bytes()).hexdigest()
            if source.is_file()
            else None
        )
        if actual != expected:
            metadata["source_drift"][relative] = {
                "expected": expected,
                "actual": actual,
            }
    if analysis_source not in protocol["source_digests"]:
        source = ROOT / analysis_source
        metadata["source_drift"][analysis_source] = {
            "expected": None,
            "actual": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    if metadata["rule_drift"] and not allow_drift:
        raise ValueError("analysis rules differ from predeclaration")
    if metadata["source_drift"] and not allow_drift:
        raise ValueError("source differs from predeclaration")
    metadata["predeclaration_status"] = (
        "exploratory_reanalysis"
        if metadata["rule_drift"] or metadata["source_drift"]
        else "verified"
    )
    tasks = [task["task_id"] for task in protocol["tasks"]]
    return report, tasks, metadata
