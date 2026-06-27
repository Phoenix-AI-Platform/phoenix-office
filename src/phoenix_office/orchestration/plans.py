"""Dry-run orchestration plan contract models.

These Pydantic models describe proposed workflow plans before human approval.
They are contract-only skeletons: they do not execute commands, call CLI entry
points, open SQLite databases, read records, compose proposal input, or render
DOCX files.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class WorkflowPlanStatus(StrEnum):
    """Lifecycle state for a proposed workflow plan."""

    DRY_RUN = "dry_run"


class WorkflowPlanApproval(BaseModel):
    """Human approval metadata for a dry-run workflow plan."""

    required: bool = Field(
        default=True,
        description="Whether human approval is required before future execution.",
    )
    approved: bool = Field(
        default=False,
        description="Whether the dry-run plan has been approved.",
    )
    approved_by: str | None = Field(
        default=None,
        description="Identifier for the human approver, if approval has occurred.",
    )
    notes: str | None = Field(default=None, description="Optional approval notes.")


class WorkflowPlanStep(BaseModel):
    """One proposed step in a dry-run workflow plan."""

    step_number: int = Field(..., ge=1, description="One-based step order.")
    name: str = Field(..., min_length=1, description="Human-readable step name.")
    description: str | None = Field(default=None, description="Optional step summary.")
    command: list[str] | None = Field(
        default=None,
        description="Proposed command arguments only. These are not executed.",
    )
    writes_artifact: bool = Field(
        default=False,
        description="Whether this step would write an artifact if executed later.",
    )
    artifact_path: str | None = Field(
        default=None,
        description="Expected artifact path for a future execution step.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Whether an operator should review this step's output.",
    )


class WorkflowPlan(BaseModel):
    """A proposed workflow plan for human review before execution exists."""

    workflow_name: str = Field(..., min_length=1, description="Workflow identifier.")
    description: str | None = Field(default=None, description="Optional workflow summary.")
    status: WorkflowPlanStatus = Field(
        default=WorkflowPlanStatus.DRY_RUN,
        description="Current plan status. Only dry-run plans are modeled for now.",
    )
    approval_required: bool = Field(
        default=True,
        description="Whether human approval is required before future execution.",
    )
    approval: WorkflowPlanApproval = Field(default_factory=WorkflowPlanApproval)
    steps: list[WorkflowPlanStep] = Field(
        ...,
        min_length=1,
        description="Ordered proposed workflow steps.",
    )

    @field_validator("steps")
    @classmethod
    def steps_must_be_sequential(cls, steps: list[WorkflowPlanStep]) -> list[WorkflowPlanStep]:
        for expected_number, step in enumerate(steps, start=1):
            if step.step_number != expected_number:
                raise ValueError(
                    f"Workflow step at position {expected_number} has number "
                    f"{step.step_number}; expected {expected_number}."
                )
        return steps


def create_a1_proposal_dry_run_plan(
    *,
    customer_id: str,
    job_id: str,
    details_json_path: str,
    db_path: str,
    proposal_input_output_path: str,
    docx_output_path: str,
    template_path: str,
) -> WorkflowPlan:
    """Return a dry-run plan for the current manual A-1 proposal workflow.

    The returned command arrays are proposed operator commands only. This helper
    does not run them and does not touch files, records, SQLite, proposal input,
    or DOCX rendering.
    """
    return WorkflowPlan(
        workflow_name="a1_proposal_manual_workflow",
        description=(
            "Dry-run plan for composing an A-1 ProposalInput JSON from stored "
            "records and explicit proposal details, then generating a DOCX "
            "through the existing proposal command after human review."
        ),
        status=WorkflowPlanStatus.DRY_RUN,
        approval_required=True,
        approval=WorkflowPlanApproval(required=True),
        steps=[
            WorkflowPlanStep(
                step_number=1,
                name="records proposal-details validate",
                description="Validate explicit RecordProposalDetails JSON.",
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "records",
                    "proposal-details",
                    "validate",
                    details_json_path,
                ],
                requires_human_review=True,
            ),
            WorkflowPlanStep(
                step_number=2,
                name="records proposal-input",
                description=(
                    "Compose deterministic ProposalInput JSON from stored "
                    "customer/job records plus explicit proposal details."
                ),
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "records",
                    "proposal-input",
                    customer_id,
                    job_id,
                    details_json_path,
                    proposal_input_output_path,
                    "--db",
                    db_path,
                ],
                writes_artifact=True,
                artifact_path=proposal_input_output_path,
                requires_human_review=True,
            ),
            WorkflowPlanStep(
                step_number=3,
                name="proposal validate",
                description="Validate composed ProposalInput JSON.",
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "proposal",
                    "validate",
                    proposal_input_output_path,
                ],
                requires_human_review=True,
            ),
            WorkflowPlanStep(
                step_number=4,
                name="proposal inspect",
                description="Inspect a human-readable ProposalInput summary.",
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "proposal",
                    "inspect",
                    proposal_input_output_path,
                ],
                requires_human_review=True,
            ),
            WorkflowPlanStep(
                step_number=5,
                name="proposal generate",
                description="Generate a DOCX proposal from ProposalInput and template.",
                command=[
                    "python",
                    "-m",
                    "phoenix_office.cli",
                    "proposal",
                    "generate",
                    proposal_input_output_path,
                    docx_output_path,
                    "--template",
                    template_path,
                ],
                writes_artifact=True,
                artifact_path=docx_output_path,
                requires_human_review=True,
            ),
        ],
    )
