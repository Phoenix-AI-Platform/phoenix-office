"""Tests for read-only WorkflowPlan CLI inspection."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
PLAN_FIXTURE = ROOT / "examples" / "orchestration" / "a1_proposal_dry_run_plan.json"


def test_cli_orchestration_plan_inspect_outputs_summary(capsys) -> None:
    exit_code = main(["orchestration", "plan", "inspect", str(PLAN_FIXTURE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Workflow plan: a1_proposal_manual_workflow" in captured.out
    assert "Status: dry_run" in captured.out
    assert "Approval required: yes" in captured.out
    assert "Approval approved: no" in captured.out
    assert "Steps: 5" in captured.out
    assert "Steps requiring human review: 5" in captured.out
    assert "Artifact-writing steps: 2" in captured.out
    assert "records proposal-details validate" in captured.out
    assert "proposal generate" in captured.out
    assert "Execution: not supported" in captured.out


def test_cli_orchestration_plan_inspect_fails_cleanly_for_missing_file(
    tmp_path,
    capsys,
) -> None:
    missing_plan = tmp_path / "missing-plan.json"

    exit_code = main(["orchestration", "plan", "inspect", str(missing_plan)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlan JSON file does not exist" in captured.err
    assert str(missing_plan) in captured.err


def test_cli_orchestration_plan_inspect_fails_cleanly_for_directory_path(
    tmp_path,
    capsys,
) -> None:
    exit_code = main(["orchestration", "plan", "inspect", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "WorkflowPlan JSON path is not a file" in captured.err
    assert str(tmp_path) in captured.err


def test_cli_orchestration_plan_inspect_fails_cleanly_for_invalid_json(
    tmp_path,
    capsys,
) -> None:
    invalid_json = tmp_path / "invalid-plan.json"
    invalid_json.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["orchestration", "plan", "inspect", str(invalid_json)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid JSON" in captured.err


def test_cli_orchestration_plan_inspect_fails_cleanly_for_invalid_plan(
    tmp_path,
    capsys,
) -> None:
    invalid_plan = tmp_path / "invalid-plan.json"
    invalid_plan.write_text(
        "{\n"
        '  "workflow_name": "broken_plan",\n'
        '  "status": "dry_run",\n'
        '  "steps": []\n'
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(["orchestration", "plan", "inspect", str(invalid_plan)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid WorkflowPlan" in captured.err
