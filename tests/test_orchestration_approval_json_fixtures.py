"""Tests for workflow plan review JSON fixtures."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.orchestration import (
    WorkflowPlan,
    WorkflowPlanApprovalDecision,
    WorkflowPlanReview,
)

ROOT = Path(__file__).parents[1]
ORCHESTRATION_EXAMPLES = ROOT / "examples" / "orchestration"
DRY_RUN_PLAN_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_dry_run_plan.json"
REVIEW_FIXTURES = {
    WorkflowPlanApprovalDecision.APPROVED: ORCHESTRATION_EXAMPLES
    / "a1_proposal_review_approved.json",
    WorkflowPlanApprovalDecision.REJECTED: ORCHESTRATION_EXAMPLES
    / "a1_proposal_review_rejected.json",
    WorkflowPlanApprovalDecision.NEEDS_CHANGES: ORCHESTRATION_EXAMPLES
    / "a1_proposal_review_needs_changes.json",
}


def _load_review(decision: WorkflowPlanApprovalDecision) -> WorkflowPlanReview:
    return WorkflowPlanReview.model_validate_json(
        REVIEW_FIXTURES[decision].read_text(encoding="utf-8")
    )


def test_workflow_review_fixtures_parse_with_expected_decisions() -> None:
    approved = _load_review(WorkflowPlanApprovalDecision.APPROVED)
    rejected = _load_review(WorkflowPlanApprovalDecision.REJECTED)
    needs_changes = _load_review(WorkflowPlanApprovalDecision.NEEDS_CHANGES)

    assert approved.decision == WorkflowPlanApprovalDecision.APPROVED
    assert approved.approved_for_execution is True
    assert rejected.decision == WorkflowPlanApprovalDecision.REJECTED
    assert rejected.approved_for_execution is False
    assert needs_changes.decision == WorkflowPlanApprovalDecision.NEEDS_CHANGES
    assert needs_changes.approved_for_execution is False


def test_workflow_review_fixtures_round_trip_json() -> None:
    for decision in WorkflowPlanApprovalDecision:
        review = _load_review(decision)

        round_tripped = WorkflowPlanReview.model_validate_json(
            review.model_dump_json(indent=2)
        )

        assert round_tripped == review


def test_workflow_review_fixtures_match_dry_run_plan_workflow_name() -> None:
    plan = WorkflowPlan.model_validate_json(
        DRY_RUN_PLAN_FIXTURE.read_text(encoding="utf-8")
    )

    for decision in WorkflowPlanApprovalDecision:
        review = _load_review(decision)

        assert review.workflow_name == plan.workflow_name
        assert review.reviewed_by == "human:sample-operator"
