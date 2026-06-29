"""Contract-only human approval boundary for workflow plans.

These models represent a human review decision for a dry-run workflow plan.
They do not execute commands, mutate plans, call CLI entry points, open SQLite,
read records, compose proposal input, or render DOCX files.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class WorkflowPlanApprovalDecision(StrEnum):
    """Human review decisions for dry-run workflow plans."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class WorkflowPlanReview(BaseModel):
    """A human review decision for a proposed workflow plan."""

    workflow_name: str = Field(..., min_length=1, description="Reviewed workflow name.")
    decision: WorkflowPlanApprovalDecision = Field(
        ..., description="Human decision for the reviewed workflow plan."
    )
    reviewed_by: str = Field(..., min_length=1, description="Human reviewer identifier.")
    review_notes: str | None = Field(default=None, description="Optional reviewer notes.")
    approved_for_execution: bool = Field(
        default=False,
        description="Whether a future execution layer may treat the plan as approved.",
    )
    reviewed_plan_fingerprint: str | None = Field(
        default=None,
        description=(
            "Optional SHA-256 fingerprint of the WorkflowPlan content reviewed "
            "by the human."
        ),
    )

    @model_validator(mode="after")
    def approved_for_execution_only_when_approved(self) -> Self:
        """Ensure only approved decisions can cross the execution boundary."""
        expected = self.decision == WorkflowPlanApprovalDecision.APPROVED
        if self.approved_for_execution != expected:
            raise ValueError(
                "approved_for_execution must be true only when decision is approved."
            )
        return self


def create_workflow_plan_review(
    *,
    workflow_name: str,
    decision: WorkflowPlanApprovalDecision,
    reviewed_by: str,
    review_notes: str | None = None,
    reviewed_plan_fingerprint: str | None = None,
) -> WorkflowPlanReview:
    """Return a human review contract for a dry-run workflow plan.

    This helper derives the execution approval flag from the human decision only.
    It does not mutate a WorkflowPlan or perform any workflow action.
    """
    return WorkflowPlanReview(
        workflow_name=workflow_name,
        decision=decision,
        reviewed_by=reviewed_by,
        review_notes=review_notes,
        approved_for_execution=decision == WorkflowPlanApprovalDecision.APPROVED,
        reviewed_plan_fingerprint=reviewed_plan_fingerprint,
    )
