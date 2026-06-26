"""Tests for read-only TaskEnvelope validation CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
TASK_EXAMPLE = ROOT / "examples" / "tasks" / "proposal_generation_task.json"


def _load_task_example() -> dict[str, Any]:
    return json.loads(TASK_EXAMPLE.read_text(encoding="utf-8"))


def test_cli_tasks_validate_passes_for_example(capsys):
    exit_code = main(["tasks", "validate", str(TASK_EXAMPLE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "validation passed" in captured.out
    assert "task-proposal-abby-hill" in captured.out


def test_cli_tasks_validate_does_not_require_proposal_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    exit_code = main(["tasks", "validate", str(TASK_EXAMPLE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "task-proposal-abby-hill" in captured.out


def test_cli_tasks_validate_fails_cleanly_when_json_is_invalid(tmp_path, capsys):
    invalid_task = tmp_path / "invalid-task.json"
    invalid_task.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["tasks", "validate", str(invalid_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid JSON" in captured.err


def test_cli_tasks_validate_fails_cleanly_when_json_is_not_an_object(tmp_path, capsys):
    list_task = tmp_path / "list-task.json"
    list_task.write_text("[]", encoding="utf-8")

    exit_code = main(["tasks", "validate", str(list_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "TaskEnvelope JSON must be an object" in captured.err


def test_cli_tasks_validate_reports_missing_required_fields(tmp_path, capsys):
    incomplete_task = tmp_path / "incomplete-task.json"
    incomplete_task.write_text(
        json.dumps({"task_id": "task-incomplete"}),
        encoding="utf-8",
    )

    exit_code = main(["tasks", "validate", str(incomplete_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Missing required field: title" in captured.err
    assert "Missing required field: status" in captured.err
    assert "Missing required field: requester" in captured.err
    assert "Missing required field: verification_plan" in captured.err


def test_cli_tasks_validate_reports_unknown_capability_id(tmp_path, capsys):
    task = _load_task_example()
    task["allowed_resources"]["capabilities"] = ["missing.capability"]
    task_path = tmp_path / "unknown-capability-task.json"
    task_path.write_text(json.dumps(task), encoding="utf-8")

    exit_code = main(["tasks", "validate", str(task_path)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Unknown capability id: missing.capability" in captured.err
