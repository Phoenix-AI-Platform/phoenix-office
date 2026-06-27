"""Tests for workflow plan human approval boundary contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from phoenix_office.orchestration import (
    WorkflowPlan,
    WorkflowPlanApprovalDecision,
    WorkflowPlanReview,
    create_workflow_plan_review,
)

ROOT = Path(__file__).parents[1]
PLAN_FIXTURE = ROOT / "examples" / "orchestration" / "a1_proposal_dry_run_plan.json"


def test_approved_review_is_approved_for_execution() -> None:
    review = WorkflowPlanReview(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.APPROVED,
        reviewed_by="human:matt",
        review_notes="Ready for operator-controlled execution in a future layer.",
        approved_for_execution=True,
    )

    assert review.decision == WorkflowPlanApprovalDecision.APPROVED
    assert review.approved_for_execution is True


def test_rejected_review_is_not_approved_for_execution() -> None:
    review = WorkflowPlanReview(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.REJECTED,
        reviewed_by="human:matt",
        review_notes="Do not proceed.",
        approved_for_execution=False,
    )

    assert review.decision == WorkflowPlanApprovalDecision.REJECTED
    assert review.approved_for_execution is False


def test_needs_changes_review_is_not_approved_for_execution() -> None:
    review = WorkflowPlanReview(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.NEEDS_CHANGES,
        reviewed_by="human:matt",
        review_notes="Revise the proposed output path before approval.",
        approved_for_execution=False,
    )

    assert review.decision == WorkflowPlanApprovalDecision.NEEDS_CHANGES
    assert review.approved_for_execution is False


def test_approval_flag_must_match_decision() -> None:
    with pytest.raises(ValueError, match="approved_for_execution"):
        WorkflowPlanReview(
            workflow_name="a1_proposal_manual_workflow",
            decision=WorkflowPlanApprovalDecision.REJECTED,
            reviewed_by="human:matt",
            approved_for_execution=True,
        )

    with pytest.raises(ValueError, match="approved_for_execution"):
        WorkflowPlanReview(
            workflow_name="a1_proposal_manual_workflow",
            decision=WorkflowPlanApprovalDecision.APPROVED,
            reviewed_by="human:matt",
            approved_for_execution=False,
        )


def test_create_workflow_plan_review_sets_execution_flag_from_decision() -> None:
    approved = create_workflow_plan_review(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.APPROVED,
        reviewed_by="human:matt",
    )
    rejected = create_workflow_plan_review(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.REJECTED,
        reviewed_by="human:matt",
    )
    needs_changes = create_workflow_plan_review(
        workflow_name="a1_proposal_manual_workflow",
        decision=WorkflowPlanApprovalDecision.NEEDS_CHANGES,
        reviewed_by="human:matt",
    )

    assert approved.approved_for_execution is True
    assert rejected.approved_for_execution is False
    assert needs_changes.approved_for_execution is False


def test_dry_run_plan_fixture_still_requires_approval() -> None:
    plan = WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))

    assert plan.workflow_name == "a1_proposal_manual_workflow"
    assert plan.approval_required is True
    assert plan.approval.required is True
    assert plan.approval.approved is False
