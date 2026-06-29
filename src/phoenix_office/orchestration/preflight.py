"""Read-only orchestration preflight reporting.

This module inspects already-validated WorkflowPlan and WorkflowPlanReview
objects together. It does not execute plans, mutate reviews, persist audit logs,
write artifacts, enqueue work, schedule retries, or render DOCX files.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from phoenix_office.orchestration.approval import (
    WorkflowPlanApprovalDecision,
    WorkflowPlanReview,
)
from phoenix_office.orchestration.plans import WorkflowPlan

EXECUTION_UNAVAILABLE_MESSAGE = (
    "Execution is unavailable: orchestration preflight is read-only and "
    "does not implement execution."
)


def workflow_plan_fingerprint(plan: WorkflowPlan) -> str:
    """Return a deterministic SHA-256 fingerprint for a WorkflowPlan."""

    payload = json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PreflightIssue(BaseModel):
    """A deterministic preflight issue for a plan/review pair."""

    code: str = Field(..., min_length=1, description="Stable issue code.")
    message: str = Field(..., min_length=1, description="Human-readable issue text.")
    blocking: bool = Field(
        default=True,
        description="Whether the issue blocks considering the pair for execution.",
    )


class PreflightReport(BaseModel):
    """Read-only preflight result for a WorkflowPlan and WorkflowPlanReview."""

    plan_workflow_name: str
    plan_fingerprint: str
    reviewed_plan_fingerprint: str | None
    plan_fingerprint_matches_review: bool | None
    review_workflow_name: str
    review_decision: WorkflowPlanApprovalDecision
    approved_for_execution: bool
    plan_valid: bool = True
    review_valid: bool = True
    execution_available: bool = False
    execution_message: str = EXECUTION_UNAVAILABLE_MESSAGE
    safe_to_consider_for_future_execution: bool
    issues: list[PreflightIssue] = Field(default_factory=list)

    @property
    def has_blocking_issues(self) -> bool:
        """Return whether any preflight issue blocks future execution consideration."""

        return any(issue.blocking for issue in self.issues)


def run_orchestration_preflight(
    plan: WorkflowPlan,
    review: WorkflowPlanReview,
) -> PreflightReport:
    """Inspect a plan/review pair without executing or mutating anything."""

    issues: list[PreflightIssue] = []
    plan_fingerprint = workflow_plan_fingerprint(plan)
    reviewed_plan_fingerprint = review.reviewed_plan_fingerprint

    if review.decision != WorkflowPlanApprovalDecision.APPROVED:
        issues.append(
            PreflightIssue(
                code="review_not_approved",
                message=(
                    "WorkflowPlanReview decision must be approved before the "
                    "plan can be considered for future execution."
                ),
            )
        )

    if not review.approved_for_execution:
        issues.append(
            PreflightIssue(
                code="review_not_marked_approved_for_execution",
                message=(
                    "WorkflowPlanReview approved_for_execution must be true "
                    "before the plan can be considered for future execution."
                ),
            )
        )

    if plan.workflow_name != review.workflow_name:
        issues.append(
            PreflightIssue(
                code="workflow_name_mismatch",
                message=(
                    "WorkflowPlan and WorkflowPlanReview workflow_name values "
                    "must match before the pair can be considered together."
                ),
            )
        )

    if reviewed_plan_fingerprint is None:
        plan_fingerprint_matches_review = None
        issues.append(
            PreflightIssue(
                code="review_plan_fingerprint_missing",
                message=(
                    "WorkflowPlanReview reviewed_plan_fingerprint must be set "
                    "before the pair can be considered together."
                ),
            )
        )
    else:
        plan_fingerprint_matches_review = reviewed_plan_fingerprint == plan_fingerprint
        if not plan_fingerprint_matches_review:
            issues.append(
                PreflightIssue(
                    code="review_plan_fingerprint_mismatch",
                    message=(
                        "WorkflowPlanReview reviewed_plan_fingerprint must match "
                        "the current WorkflowPlan fingerprint."
                    ),
                )
            )

    has_blocking_issues = any(issue.blocking for issue in issues)
    return PreflightReport(
        plan_workflow_name=plan.workflow_name,
        plan_fingerprint=plan_fingerprint,
        reviewed_plan_fingerprint=reviewed_plan_fingerprint,
        plan_fingerprint_matches_review=plan_fingerprint_matches_review,
        review_workflow_name=review.workflow_name,
        review_decision=review.decision,
        approved_for_execution=review.approved_for_execution,
        safe_to_consider_for_future_execution=not has_blocking_issues,
        issues=issues,
    )
