"""Tests for read-only Codex handoff package CLI inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
HANDOFF_EXAMPLE = ROOT / "examples" / "tasks" / "codex_handoff_package.json"


def _load_example() -> dict[str, Any]:
    return json.loads(HANDOFF_EXAMPLE.read_text(encoding="utf-8"))


def _write_package(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "codex_handoff.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dev_codex_handoff_outputs_human_readable_summary(capsys):
    exit_code = main(["dev", "codex-handoff", str(HANDOFF_EXAMPLE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Codex handoff package: codex-handoff-issue-259" in captured.out
    assert "Schema version: codex-handoff-package.v1" in captured.out
    assert "Task ID: task-issue-259-codex-handoff-package" in captured.out
    assert "Task title: Add machine-readable Codex handoff package" in captured.out
    assert "Repository: Phoenix-AI-Platform/phoenix-office" in captured.out
    assert "Base branch: main" in captured.out
    assert "Expected PR title: feat: add machine-readable Codex handoff package" in captured.out
    assert "Worker type: codex" in captured.out
    assert "Invocation mode: manual" in captured.out
    assert "Invocation authorized: no" in captured.out
    assert "Review required: yes" in captured.out
    assert "Worker may merge: no" in captured.out
    assert "Required repository paths:" in captured.out
    assert "Required PR body headings:" in captured.out
    assert "Prompt:" in captured.out
    assert "Codex invocation: not authorized" in captured.out
    assert "Merge behavior: not authorized" in captured.out
    assert captured.err == ""


def test_dev_codex_handoff_json_outputs_valid_package(capsys):
    exit_code = main(["dev", "codex-handoff", str(HANDOFF_EXAMPLE), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["handoff_id"] == "codex-handoff-issue-259"
    assert payload["worker_type"] == "codex"
    assert payload["invocation_mode"] == "manual"
    assert payload["invocation_authorized"] is False
    assert captured.err == ""


def test_dev_codex_handoff_json_output_equals_loaded_package(capsys):
    expected = _load_example()

    exit_code = main(["dev", "codex-handoff", str(HANDOFF_EXAMPLE), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == expected


def test_dev_codex_handoff_missing_file_fails_cleanly(tmp_path, capsys):
    missing_path = tmp_path / "missing.json"

    exit_code = main(["dev", "codex-handoff", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "CodexHandoffPackage JSON file does not exist" in captured.err


def test_dev_codex_handoff_directory_path_fails_cleanly(tmp_path, capsys):
    exit_code = main(["dev", "codex-handoff", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "CodexHandoffPackage JSON path is not a file" in captured.err


def test_dev_codex_handoff_invalid_json_fails_cleanly(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid JSON" in captured.err


def test_dev_codex_handoff_non_object_json_fails_cleanly(tmp_path, capsys):
    path = _write_package(tmp_path, [])

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "CodexHandoffPackage JSON must be an object" in captured.err


def test_dev_codex_handoff_unsupported_schema_version_fails_closed(tmp_path, capsys):
    package = _load_example()
    package["schema_version"] = "codex-handoff-package.v2"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "schema_version must be 'codex-handoff-package.v1'" in captured.err


def test_dev_codex_handoff_missing_required_field_fails_closed(tmp_path, capsys):
    package = _load_example()
    del package["expected_pr_title"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "expected_pr_title must be a non-empty string" in captured.err


def test_dev_codex_handoff_invocation_authorized_true_fails_closed(
    tmp_path, capsys
):
    package = _load_example()
    package["invocation_authorized"] = True
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "invocation_authorized must be False" in captured.err


def test_dev_codex_handoff_review_required_false_fails_closed(tmp_path, capsys):
    package = _load_example()
    package["review_required"] = False
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "review_required must be True" in captured.err


def test_dev_codex_handoff_worker_may_merge_true_fails_closed(tmp_path, capsys):
    package = _load_example()
    package["worker_may_merge"] = True
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "worker_may_merge must be False" in captured.err


def test_dev_codex_handoff_wrong_worker_type_fails_closed(tmp_path, capsys):
    package = _load_example()
    package["worker_type"] = "browser"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "worker_type must be 'codex'" in captured.err


def test_dev_codex_handoff_wrong_invocation_mode_fails_closed(tmp_path, capsys):
    package = _load_example()
    package["invocation_mode"] = "automatic"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "invocation_mode must be 'manual'" in captured.err


def test_dev_codex_handoff_non_string_required_list_item_fails_closed(
    tmp_path, capsys
):
    package = _load_example()
    package["required_repo_paths"] = ["AGENTS.md", 42]
    package["required_pr_body_headings"] = ["Summary", None]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-handoff", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "required_repo_paths must contain only strings" in captured.err
    assert "required_pr_body_headings must contain only strings" in captured.err
