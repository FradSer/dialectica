"""Grounding gates validate supplied evidence, not open-ended decision quality."""

import json

from evals.evidence_tasks import make_evidence_tasks


def test_grounding_rejects_fabricated_quotes_and_unknown_sources():
    task = make_evidence_tasks("dev", 1)[0]
    answer = {
        "decision": "Choose a bounded pilot.",
        "trigger": "Stop if the supplied cost cap is exceeded.",
        "claims": [
            {
                "source_id": "S1",
                "quote": task.sources["S1"],
                "inference": "Limited capacity.",
            }
        ],
        "risks": ["Schedule risk"],
        "assumptions": [],
    }
    assert task.verify_content(json.dumps(answer)) == (True, "")
    answer["claims"][0]["quote"] = "The board has approved unlimited funding."
    assert not task.verify_content(json.dumps(answer))[0]
    answer["claims"][0]["source_id"] = "S99"
    assert not task.verify_content(json.dumps(answer))[0]


def test_evidence_task_splits_are_deterministic_and_explicitly_synthetic():
    dev = make_evidence_tasks("dev", 4)
    held = make_evidence_tasks("heldout", 4)
    assert dev == make_evidence_tasks("dev", 4)
    assert {t.sources["S1"] for t in dev}.isdisjoint(t.sources["S1"] for t in held)
    assert all("synthetic" in t.statement.lower() for t in dev + held)
