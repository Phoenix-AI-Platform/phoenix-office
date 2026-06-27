"""Tests for dry-run orchestration plan contract models."""

from pathlib import Path

import pytest

from phoenix_office.orchestration import (
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowPlanStep,
    create_a1_proposal_dry_run_plan,
)


def test_workflow_plan_can_be_constructed() -> None:
    plan = WorkflowPlan(
        workflow_name="test_workflow",
        description="A dry-run test workflow.",
        steps=[
            WorkflowPlanStep(
                step_number=1,
                name="inspect input",
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "proposal",
                    "inspect",
                ],
                requires_human_review=True,
            )
        ],
    )

    assert plan.workflow_name == "test_workflow"
    assert plan.status == WorkflowPlanStatus.DRY_RUN
    assert plan.approval_required is True
    assert plan.approval.required is True
    assert plan.approval.approved is False
    assert plan.steps[0].name == "inspect input"


def test_workflow_plan_rejects_non_sequential_steps() -> None:
    with pytest.raises(ValueError, match="expected 1"):
        WorkflowPlan(
            workflow_name="bad_workflow",
            steps=[WorkflowPlanStep(step_number=2, name="out of order")],
        )


def test_a1_proposal_dry_run_plan_has_expected_sequence(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    proposal_input_path = tmp_path / "nested" / "proposal_input.json"
    docx_output_path = tmp_path / "nested" / "proposal.docx"

    plan = create_a1_proposal_dry_run_plan(
        customer_id="customer-abby-hill",
        job_id="job-abby-hill",
        details_json_path="examples/records/proposal_details_abby_hill.json",
        db_path=str(db_path),
        proposal_input_output_path=str(proposal_input_path),
        docx_output_path=str(docx_output_path),
        template_path="tests/fixtures/templates/a1_proposal_template.docx",
    )

    assert plan.status == WorkflowPlanStatus.DRY_RUN
    assert plan.approval_required is True
    assert [step.name for step in plan.steps] == [
        "records proposal-details validate",
        "records proposal-input",
        "proposal validate",
        "proposal inspect",
        "proposal generate",
    ]
    assert [step.step_number for step in plan.steps] == [1, 2, 3, 4, 5]


def test_a1_proposal_dry_run_plan_marks_artifact_steps(tmp_path: Path) -> None:
    proposal_input_path = tmp_path / "proposal_input.json"
    docx_output_path = tmp_path / "proposal.docx"

    plan = create_a1_proposal_dry_run_plan(
        customer_id="customer-abby-hill",
        job_id="job-abby-hill",
        details_json_path="examples/records/proposal_details_abby_hill.json",
        db_path=str(tmp_path / "records.sqlite"),
        proposal_input_output_path=str(proposal_input_path),
        docx_output_path=str(docx_output_path),
        template_path="tests/fixtures/templates/a1_proposal_template.docx",
    )

    proposal_input_step = plan.steps[1]
    generate_step = plan.steps[4]

    assert proposal_input_step.writes_artifact is True
    assert proposal_input_step.artifact_path == str(proposal_input_path)
    assert generate_step.writes_artifact is True
    assert generate_step.artifact_path == str(docx_output_path)


def test_a1_proposal_dry_run_plan_contains_proposed_commands_only(
    tmp_path: Path,
) -> None:
    plan = create_a1_proposal_dry_run_plan(
        customer_id="customer-abby-hill",
        job_id="job-abby-hill",
        details_json_path="examples/records/proposal_details_abby_hill.json",
        db_path=str(tmp_path / "records.sqlite"),
        proposal_input_output_path=str(tmp_path / "proposal_input.json"),
        docx_output_path=str(tmp_path / "proposal.docx"),
        template_path="tests/fixtures/templates/a1_proposal_template.docx",
    )

    assert plan.steps[0].command == [
        "python",
        "-m",
        "phoenix_office.cli",
        "records",
        "proposal-details",
        "validate",
        "examples/records/proposal_details_abby_hill.json",
    ]
    assert plan.steps[1].command is not None
    assert any("records.sqlite" in part for part in plan.steps[1].command)
    assert plan.steps[4].command is not None
    assert "--template" in plan.steps[4].command


def test_a1_proposal_dry_run_plan_has_no_file_side_effects(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    proposal_input_path = tmp_path / "nested" / "proposal_input.json"
    docx_output_path = tmp_path / "nested" / "proposal.docx"

    create_a1_proposal_dry_run_plan(
        customer_id="customer-abby-hill",
        job_id="job-abby-hill",
        details_json_path="examples/records/proposal_details_abby_hill.json",
        db_path=str(db_path),
        proposal_input_output_path=str(proposal_input_path),
        docx_output_path=str(docx_output_path),
        template_path="tests/fixtures/templates/a1_proposal_template.docx",
    )

    assert not db_path.exists()
    assert not proposal_input_path.exists()
    assert not docx_output_path.exists()
    assert not (tmp_path / "nested").exists()
