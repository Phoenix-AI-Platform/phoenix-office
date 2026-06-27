"""Tests for read-only WorkflowPlanReview CLI inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
ORCHESTRATION_EXAMPLES = ROOT / "examples" / "orchestration"
REVIEW_FIXTURES = [
    (
        "a1_proposal_review_approved.json",
        "approved",
        "yes",
        "Human reviewed the dry-run plan",
    ),
    (
        "a1_proposal_review_rejected.json",
        "rejected",
        "no",
        "Human rejected the dry-run plan",
    ),
    (
        "a1_proposal_review_needs_changes.json",
        "needs_changes",
        "no",
        "Human requested changes before approval",
    ),
]


@pytest.mark.parametrize(
    ("fixture_name", "decision", "approved_for_execution", "review_note"),
    REVIEW_FIXTURES,
)
def test_cli_orchestration_review_inspect_outputs_fixture_summary(
    fixture_name: str,
    decision: str,
    approved_for_execution: str,
    review_note: str,
    capsys,
) -> None:
    review_fixture = ORCHESTRATION_EXAMPLES / fixture_name

    exit_code = main(["orchestration", "review", "inspect", str(review_fixture)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Workflow review: a1_proposal_manual_workflow" in captured.out
    assert f"Review decision: {decision}" in captured.out
    assert f"Approved for execution: {approved_for_execution}" in captured.out
    assert "Reviewer: human:sample-operator" in captured.out
    assert review_note in captured.out
    assert "Execution: not supported" in captured.out
    assert "Approval mutation: not supported" in captured.out


def test_cli_orchestration_review_inspect_fails_cleanly_for_missing_file(
    tmp_path,
    capsys,
) -> None:
    missing_review = tmp_path / "missing-review.json"

    exit_code = main(["orchestration", "review", "inspect", str(missing_review)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlanReview JSON file does not exist" in captured.err
    assert str(missing_review) in captured.err


def test_cli_orchestration_review_inspect_fails_cleanly_for_directory_path(
    tmp_path,
    capsys,
) -> None:
    exit_code = main(["orchestration", "review", "inspect", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlanReview JSON path is not a file" in captured.err
    assert str(tmp_path) in captured.err


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
