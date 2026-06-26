"""Tests for read-only TaskEnvelope JSON CLI inspection."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
TASK_EXAMPLE = ROOT / "examples" / "tasks" / "proposal_generation_task.json"


def test_cli_tasks_show_outputs_task_summary(capsys):
    exit_code = main(["tasks", "show", str(TASK_EXAMPLE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "task-proposal-abby-hill" in captured.out
    assert "Generate proposal" in captured.out
    assert "requested" in captured.out
    assert "normal" in captured.out
    assert "human" in captured.out
    assert "human:matt" in captured.out
    assert "office.generate_proposal" in captured.out
    assert "examples/proposals/abby_hill.json" in captured.out
    assert "output/abby_hill_proposal.docx" in captured.out
    assert "artifact" in captured.out


def test_cli_tasks_show_json_outputs_loaded_task(capsys):
    exit_code = main(["tasks", "show", str(TASK_EXAMPLE), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["task_id"] == "task-proposal-abby-hill"


def test_cli_tasks_show_does_not_require_proposal_files(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)

    exit_code = main(["tasks", "show", str(TASK_EXAMPLE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "task-proposal-abby-hill" in captured.out


def test_cli_tasks_show_fails_cleanly_when_file_is_missing(tmp_path, capsys):
    missing_task = tmp_path / "missing-task.json"

    exit_code = main(["tasks", "show", str(missing_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "TaskEnvelope JSON file does not exist" in captured.err


def test_cli_tasks_show_fails_cleanly_when_json_is_invalid(tmp_path, capsys):
    invalid_task = tmp_path / "invalid-task.json"
    invalid_task.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["tasks", "show", str(invalid_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Invalid JSON" in captured.err


def test_cli_tasks_show_fails_cleanly_when_json_is_not_an_object(tmp_path, capsys):
    list_task = tmp_path / "list-task.json"
    list_task.write_text("[]", encoding="utf-8")

    exit_code = main(["tasks", "show", str(list_task)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "TaskEnvelope JSON must be an object" in captured.err
