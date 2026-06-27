"""Tests for read-only WorkflowPlanReview CLI inspection."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
REVIEW_FIXTURE = (
    ROOT / "examples" / "orchestration" / "a1_proposal_review_approved.json"
)


def test_cli_orchestration_review_inspect_outputs_summary(capsys) -> None:
    exit_code = main(["orchestration", "review", "inspect", str(REVIEW_FIXTURE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Workflow review: a1_proposal_manual_workflow" in captured.out
    assert "Review decision: approved" in captured.out
    assert "Approved for execution: yes" in captured.out
    assert "Reviewer: human:sample-operator" in captured.out
    assert "Human reviewed the dry-run plan" in captured.out
    assert "Execution: not supported" in captured.out
    assert "Approval mutation: not supported" in captured.out


def test_cli_orchestration_review_inspect_fails_cleanly_for_invalid_json(
    tmp_path,
    capsys,
) -> None:
    invalid_json = tmp_path / "invalid-review.json"
    invalid_json.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["orchestration", "review", "inspect", str(invalid_json)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid JSON" in captured.err


def test_cli_orchestration_review_inspect_fails_cleanly_for_invalid_review(
    tmp_path,
    capsys,
) -> None:
    invalid_review = tmp_path / "invalid-review.json"
    invalid_review.write_text(
        "{\n"
        '  "workflow_name": "a1_proposal_manual_workflow",\n'
        '  "decision": "approved",\n'
        '  "reviewed_by": "human:sample-operator",\n'
        '  "approved_for_execution": false\n'
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(["orchestration", "review", "inspect", str(invalid_review)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid WorkflowPlanReview" in captured.err
