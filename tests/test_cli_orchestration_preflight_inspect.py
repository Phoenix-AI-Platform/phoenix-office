"""Tests for read-only orchestration preflight CLI inspection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phoenix_office.cli import build_parser, main
from phoenix_office.orchestration import WorkflowPlan, workflow_plan_fingerprint

ROOT = Path(__file__).parents[1]
ORCHESTRATION_EXAMPLES = ROOT / "examples" / "orchestration"
PLAN_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_dry_run_plan.json"
APPROVED_REVIEW_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_review_approved.json"
REJECTED_REVIEW_FIXTURE = ORCHESTRATION_EXAMPLES / "a1_proposal_review_rejected.json"
NEEDS_CHANGES_REVIEW_FIXTURE = (
    ORCHESTRATION_EXAMPLES / "a1_proposal_review_needs_changes.json"
)
EXECUTION_UNAVAILABLE_MESSAGE = (
    "Execution is unavailable: orchestration preflight is read-only and "
    "does not implement execution."
)


def _plan_fingerprint() -> str:
    plan = WorkflowPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    return workflow_plan_fingerprint(plan)


def test_cli_orchestration_preflight_inspect_outputs_approved_summary(capsys) -> None:
    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(APPROVED_REVIEW_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Orchestration preflight: a1_proposal_manual_workflow" in captured.out
    assert "Plan workflow: a1_proposal_manual_workflow" in captured.out
    assert f"Plan fingerprint: {_plan_fingerprint()}" in captured.out
    assert f"Reviewed plan fingerprint: {_plan_fingerprint()}" in captured.out
    assert "Plan fingerprint matches review: yes" in captured.out
    assert "Review workflow: a1_proposal_manual_workflow" in captured.out
    assert "Review decision: approved" in captured.out
    assert "Approved for execution: yes" in captured.out
    assert "Execution available: no" in captured.out
    assert (
        "Execution message: Execution is unavailable: orchestration preflight "
        "is read-only and does not implement execution."
    ) in captured.out
    assert "Blocking issues: no" in captured.out
    assert "Issues:" in captured.out
    assert "  - (none)" in captured.out
    assert "Execution: not supported" in captured.out


@pytest.mark.parametrize(
    ("review_fixture", "decision"),
    [
        (REJECTED_REVIEW_FIXTURE, "rejected"),
        (NEEDS_CHANGES_REVIEW_FIXTURE, "needs_changes"),
    ],
)
def test_cli_orchestration_preflight_inspect_outputs_blocking_issue_codes(
    review_fixture: Path,
    decision: str,
    capsys,
) -> None:
    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(review_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Review decision: {decision}" in captured.out
    assert "Plan fingerprint matches review: yes" in captured.out
    assert "Blocking issues: yes" in captured.out
    assert "review_not_approved: WorkflowPlanReview decision must be approved" in captured.out
    assert (
        "review_not_marked_approved_for_execution: WorkflowPlanReview "
        "approved_for_execution must be true"
    ) in captured.out
    assert "Execution: not supported" in captured.out


def test_cli_orchestration_preflight_inspect_outputs_workflow_mismatch_issue(
    tmp_path: Path,
    capsys,
) -> None:
    review_payload = json.loads(APPROVED_REVIEW_FIXTURE.read_text(encoding="utf-8"))
    review_payload["workflow_name"] = "other_workflow"
    mismatched_review = tmp_path / "mismatched-review.json"
    mismatched_review.write_text(
        f"{json.dumps(review_payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(mismatched_review),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Review workflow: other_workflow" in captured.out
    assert "Plan fingerprint matches review: yes" in captured.out
    assert "Blocking issues: yes" in captured.out
    assert "workflow_name_mismatch" in captured.out


def test_cli_orchestration_preflight_inspect_json_outputs_approved_report(capsys) -> None:
    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(APPROVED_REVIEW_FIXTURE),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload == {
        "approved_for_execution": True,
        "execution_available": False,
        "execution_message": EXECUTION_UNAVAILABLE_MESSAGE,
        "issues": [],
        "plan_fingerprint": _plan_fingerprint(),
        "plan_fingerprint_matches_review": True,
        "plan_valid": True,
        "plan_workflow_name": "a1_proposal_manual_workflow",
        "review_decision": "approved",
        "review_valid": True,
        "review_workflow_name": "a1_proposal_manual_workflow",
        "reviewed_plan_fingerprint": _plan_fingerprint(),
        "safe_to_consider_for_future_execution": True,
    }
    assert captured.out.endswith("\n")
    assert captured.err == ""


@pytest.mark.parametrize(
    ("review_fixture", "decision"),
    [
        (REJECTED_REVIEW_FIXTURE, "rejected"),
        (NEEDS_CHANGES_REVIEW_FIXTURE, "needs_changes"),
    ],
)
def test_cli_orchestration_preflight_inspect_json_outputs_blocking_issue_codes(
    review_fixture: Path,
    decision: str,
    capsys,
) -> None:
    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(review_fixture),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["plan_fingerprint"] == _plan_fingerprint()
    assert payload["reviewed_plan_fingerprint"] == _plan_fingerprint()
    assert payload["plan_fingerprint_matches_review"] is True
    assert payload["review_decision"] == decision
    assert payload["execution_available"] is False
    assert payload["safe_to_consider_for_future_execution"] is False
    assert [issue["code"] for issue in payload["issues"]] == [
        "review_not_approved",
        "review_not_marked_approved_for_execution",
    ]
    assert all(issue["blocking"] for issue in payload["issues"])
    assert captured.err == ""


def test_cli_orchestration_preflight_inspect_json_outputs_workflow_mismatch_issue(
    tmp_path: Path,
    capsys,
) -> None:
    review_payload = json.loads(APPROVED_REVIEW_FIXTURE.read_text(encoding="utf-8"))
    review_payload["workflow_name"] = "other_workflow"
    mismatched_review = tmp_path / "mismatched-review.json"
    mismatched_review.write_text(
        f"{json.dumps(review_payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(mismatched_review),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["plan_fingerprint"] == _plan_fingerprint()
    assert payload["reviewed_plan_fingerprint"] == _plan_fingerprint()
    assert payload["plan_fingerprint_matches_review"] is True
    assert payload["review_workflow_name"] == "other_workflow"
    assert payload["safe_to_consider_for_future_execution"] is False
    assert [issue["code"] for issue in payload["issues"]] == [
        "workflow_name_mismatch"
    ]
    assert payload["issues"][0]["blocking"] is True
    assert captured.err == ""


def test_cli_orchestration_preflight_inspect_json_outputs_fingerprint_mismatch_issue(
    tmp_path: Path,
    capsys,
) -> None:
    review_payload = json.loads(APPROVED_REVIEW_FIXTURE.read_text(encoding="utf-8"))
    review_payload["reviewed_plan_fingerprint"] = "not-the-current-plan"
    mismatched_review = tmp_path / "mismatched-fingerprint-review.json"
    mismatched_review.write_text(
        f"{json.dumps(review_payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(mismatched_review),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["reviewed_plan_fingerprint"] == "not-the-current-plan"
    assert payload["plan_fingerprint_matches_review"] is False
    assert [issue["code"] for issue in payload["issues"]] == [
        "review_plan_fingerprint_mismatch"
    ]
    assert captured.err == ""


def test_cli_orchestration_preflight_inspect_fails_cleanly_for_missing_plan(
    tmp_path: Path,
    capsys,
) -> None:
    missing_plan = tmp_path / "missing-plan.json"

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(missing_plan),
            str(APPROVED_REVIEW_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlan JSON file does not exist" in captured.err
    assert str(missing_plan) in captured.err


def test_cli_orchestration_preflight_inspect_fails_cleanly_for_missing_review(
    tmp_path: Path,
    capsys,
) -> None:
    missing_review = tmp_path / "missing-review.json"

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(missing_review),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlanReview JSON file does not exist" in captured.err
    assert str(missing_review) in captured.err


def test_cli_orchestration_preflight_inspect_fails_cleanly_for_directory_path(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(tmp_path),
            str(APPROVED_REVIEW_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlan JSON path is not a file" in captured.err
    assert str(tmp_path) in captured.err


def test_cli_orchestration_preflight_inspect_fails_cleanly_for_invalid_json(
    tmp_path: Path,
    capsys,
) -> None:
    invalid_json = tmp_path / "invalid-plan.json"
    invalid_json.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(invalid_json),
            str(APPROVED_REVIEW_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid JSON" in captured.err


def test_cli_orchestration_preflight_inspect_fails_cleanly_for_invalid_model(
    tmp_path: Path,
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

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(invalid_review),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid WorkflowPlanReview" in captured.err


def test_cli_orchestration_preflight_inspect_json_invalid_input_emits_no_partial_json(
    tmp_path: Path,
    capsys,
) -> None:
    invalid_review = tmp_path / "invalid-review.json"
    invalid_review.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(invalid_review),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "Invalid JSON" in captured.err


def test_cli_orchestration_preflight_inspect_does_not_create_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    assert list(tmp_path.iterdir()) == []

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(APPROVED_REVIEW_FIXTURE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


def test_cli_orchestration_preflight_inspect_json_does_not_create_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    assert list(tmp_path.iterdir()) == []

    exit_code = main(
        [
            "orchestration",
            "preflight",
            "inspect",
            str(PLAN_FIXTURE),
            str(APPROVED_REVIEW_FIXTURE),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["execution_available"] is False
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "argv",
    [
        ["orchestration", "preflight", "execute"],
        ["orchestration", "preflight", "run"],
        ["orchestration", "preflight", "apply"],
        ["orchestration", "preflight", "approve"],
        ["orchestration", "preflight", "reject"],
    ],
)
def test_orchestration_preflight_execution_and_mutation_commands_are_rejected(
    argv: list[str],
    capsys,
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)

    captured = capsys.readouterr()
    assert exc_info.value.code != 0
    assert (
        "invalid choice" in captured.err
        or "unrecognized arguments" in captured.err
    )
