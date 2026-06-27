"""Tests for the dry-run orchestration plan JSON example."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.orchestration import WorkflowPlan, WorkflowPlanStatus

ROOT = Path(__file__).parents[1]
PLAN_FIXTURE = ROOT / "examples" / "orchestration" / "a1_proposal_dry_run_plan.json"

EXPECTED_STEP_NAMES = [
    "records proposal-details validate",
    "records proposal-input",
    "proposal validate",
    "proposal inspect",
    "proposal generate",
]


def test_a1_proposal_dry_run_plan_fixture_parses_as_workflow_plan() -> None:
    payload = json.loads(PLAN_FIXTURE.read_text(encoding="utf-8"))

    plan = WorkflowPlan.model_validate(payload)

    assert plan.status == WorkflowPlanStatus.DRY_RUN
    assert plan.approval_required is True
    assert plan.approval.required is True
    assert [step.name for step in plan.steps] == EXPECTED_STEP_NAMES


def test_a1_proposal_dry_run_plan_fixture_marks_docx_artifact() -> None:
    plan = WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))

    generate_step = plan.steps[-1]

    assert generate_step.name == "proposal generate"
    assert generate_step.writes_artifact is True
    assert generate_step.artifact_path is not None
    assert generate_step.artifact_path.endswith(".docx")


def test_a1_proposal_dry_run_plan_fixture_round_trips_json() -> None:
    plan = WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))

    round_tripped = WorkflowPlan.model_validate_json(
        plan.model_dump_json(indent=2, exclude_none=False)
    )

    assert [step.name for step in round_tripped.steps] == EXPECTED_STEP_NAMES
    assert round_tripped.status == WorkflowPlanStatus.DRY_RUN
    assert round_tripped.approval_required is True


def test_a1_proposal_dry_run_plan_fixture_parsing_has_no_artifact_side_effects() -> None:
    plan = WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    artifact_paths = [
        Path(step.artifact_path)
        for step in plan.steps
        if step.artifact_path is not None
    ]
    before = {artifact_path: artifact_path.exists() for artifact_path in artifact_paths}

    WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))

    after = {artifact_path: artifact_path.exists() for artifact_path in artifact_paths}
    assert artifact_paths
    assert after == before
