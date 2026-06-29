"""Tests for non-executing orchestration preflight reporting."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.orchestration import (
    WorkflowPlan,
    WorkflowPlanApprovalDecision,
    WorkflowPlanReview,
    run_orchestration_preflight,
    workflow_plan_fingerprint,
)

ROOT = Path(__file__).parents[1]
ORCHESTRATION_EXAMPLES = ROOT / "examples" / "orchestration"
PLAN_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_dry_run_plan.json"
APPROVED_REVIEW_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_review_approved.json"
REJECTED_REVIEW_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_review_rejected.json"
NEEDS_CHANGES_REVIEW_FIXTURE = (
    ORCHESTRATION_EXAMPLES / "a1_proposal_review_needs_changes.json"
)


def _load_plan() -> WorkflowPlan:
    return WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))


def _load_review(path: Path) -> WorkflowPlanReview:
    return WorkflowPlanReview.model_validate_json(path.read_text(encoding="utf-8"))


def test_workflow_plan_fingerprint_is_stable_across_repeated_calls() -> None:
    plan = _load_plan()

    assert workflow_plan_fingerprint(plan) == workflow_plan_fingerprint(plan)
    assert workflow_plan_fingerprint(plan) == workflow_plan_fingerprint(_load_plan())


def test_workflow_plan_fingerprint_changes_when_plan_content_changes() -> None:
    plan = _load_plan()
    changed_plan = plan.model_copy(update={"workflow_name": "changed_workflow"})

    assert workflow_plan_fingerprint(changed_plan) != workflow_plan_fingerprint(plan)


def test_preflight_approved_review_is_deterministic_but_execution_unavailable() -> None:
    plan = _load_plan()
    report = run_orchestration_preflight(
        plan,
        _load_review(APPROVED_REVIEW_FIXTURE),
    )

    assert report.model_dump(mode="json") == {
        "approved_for_execution": True,
        "execution_available": False,
        "execution_message": (
            "Execution is unavailable: orchestration preflight is read-only and "
            "does not implement execution."
        ),
        "issues": [],
        "plan_fingerprint": workflow_plan_fingerprint(plan),
        "plan_valid": True,
        "plan_workflow_name": "a1_proposal_manual_workflow",
        "review_decision": "approved",
        "review_valid": True,
        "review_workflow_name": "a1_proposal_manual_workflow",
        "safe_to_consider_for_future_execution": True,
    }
    assert report.plan_fingerprint == workflow_plan_fingerprint(plan)
    assert report.has_blocking_issues is False


def test_preflight_rejected_review_returns_blocking_issue() -> None:
    report = run_orchestration_preflight(
        _load_plan(),
        _load_review(REJECTED_REVIEW_FIXTURE),
    )

    assert report.safe_to_consider_for_future_execution is False
    assert report.has_blocking_issues is True
    assert report.review_decision == WorkflowPlanApprovalDecision.REJECTED
    assert [issue.code for issue in report.issues] == [
        "review_not_approved",
        "review_not_marked_approved_for_execution",
    ]
    assert all(issue.blocking for issue in report.issues)


def test_preflight_needs_changes_review_returns_blocking_issue() -> None:
    report = run_orchestration_preflight(
        _load_plan(),
        _load_review(NEEDS_CHANGES_REVIEW_FIXTURE),
    )

    assert report.safe_to_consider_for_future_execution is False
    assert report.has_blocking_issues is True
    assert report.review_decision == WorkflowPlanApprovalDecision.NEEDS_CHANGES
    assert [issue.code for issue in report.issues] == [
        "review_not_approved",
        "review_not_marked_approved_for_execution",
    ]
    assert all(issue.blocking for issue in report.issues)


def test_preflight_report_output_is_stable() -> None:
    first = run_orchestration_preflight(
        _load_plan(),
        _load_review(APPROVED_REVIEW_FIXTURE),
    )
    second = run_orchestration_preflight(
        _load_plan(),
        _load_review(APPROVED_REVIEW_FIXTURE),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.model_dump_json() == second.model_dump_json()


def test_preflight_does_not_create_generated_artifacts(tmp_path: Path) -> None:
    assert list(tmp_path.iterdir()) == []

    report = run_orchestration_preflight(
        _load_plan(),
        _load_review(APPROVED_REVIEW_FIXTURE),
    )

    assert report.execution_available is False
    assert list(tmp_path.iterdir()) == []
