"""Tests for the proposal-generation TaskEnvelope JSON example."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.tasks.proposals import (
    PROPOSAL_GENERATION_CAPABILITY_ID,
    create_proposal_generation_task_envelope,
)

FIXTURE_PATH = Path("examples/tasks/proposal_generation_task.json")
TASK_ID = "task-proposal-abby-hill"
REQUESTER_ID = "human:matt"
INPUT_REF = "examples/proposals/abby_hill.json"
OUTPUT_REF = "output/abby_hill_proposal.docx"
TEMPLATE_REF = "tests/fixtures/templates/a1_proposal_template.docx"


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _without_dynamic_timestamps(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    normalized.pop("created_at", None)
    normalized.pop("updated_at", None)
    return normalized


def test_proposal_generation_task_example_has_expected_metadata():
    data = _load_fixture()

    assert data["task_id"] == TASK_ID
    assert data["title"] == "Generate proposal"
    assert "local proposal DOCX" in data["objective"]
    assert data["allowed_resources"]["capabilities"] == [
        PROPOSAL_GENERATION_CAPABILITY_ID
    ]
    assert data["context_refs"] == [INPUT_REF, OUTPUT_REF, TEMPLATE_REF]
    assert data["permissions"] == {
        "destructive": False,
        "execute": False,
        "network": False,
        "read": True,
        "write": True,
    }
    assert data["approval_policy"] == {"approvers": [], "required_before": []}
    assert data["verification_plan"]["evidence_required"] == ["artifact"]


def test_proposal_generation_task_example_matches_factory_static_fields():
    fixture_data = _without_dynamic_timestamps(_load_fixture())
    task = create_proposal_generation_task_envelope(
        task_id=TASK_ID,
        requester_id=REQUESTER_ID,
        input_ref=INPUT_REF,
        output_ref=OUTPUT_REF,
        template_ref=TEMPLATE_REF,
    )
    factory_data = _without_dynamic_timestamps(task.to_dict())

    assert fixture_data == factory_data
