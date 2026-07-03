"""Tests for deterministic Codex invocation request drafts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
HANDOFF_EXAMPLE = ROOT / "examples" / "tasks" / "codex_handoff_package.json"
REQUIRED_COMMANDS = [
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
]
EXPECTED_HEADINGS = [
    "Summary",
    "Scope",
    "Changed files",
    "Out-of-scope confirmation",
    "Validation performed",
    "Risks",
]


def _load_valid_request_package() -> dict[str, Any]:
    package = json.loads(HANDOFF_EXAMPLE.read_text(encoding="utf-8"))
    package["handoff_id"] = "codex-handoff-issue-279"
    package["expected_pr_title"] = (
        "feat: add deterministic Codex invocation request draft"
    )
    package["prompt"] = (
        "Use the verified Phoenix Office checkout only.\n"
        "Implement Issue #279 as one narrow PR.\n"
        "Do not invoke Codex or mutate GitHub."
    )
    package["required_pr_body_headings"] = EXPECTED_HEADINGS
    package["required_repo_paths"] = [
        "docs/process/issue-to-codex-handoff.md"
    ]
    package["task"]["task_id"] = "task-issue-279-codex-invocation-request"
    package["task"]["title"] = (
        "Add deterministic Codex invocation request draft"
    )
    package["task"]["objective"] = (
        "Draft a deterministic provider-neutral invocation request."
    )
    package["task"]["risk_class"] = "docs-only"
    package["task"]["source"] = {
        "kind": "github_issue",
        "uri": "https://github.com/Phoenix-AI-Platform/phoenix-office/issues/279",
    }
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-handoff.md"
    ]
    package["task"]["verification_plan"]["commands"] = REQUIRED_COMMANDS
    package["workspace_path"] = "C:/tmp/phoenix-office"
    return package


def _write_package(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "codex_handoff.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dev_codex_invocation_request_outputs_human_readable_draft(
    tmp_path, capsys
):
    path = _write_package(tmp_path, _load_valid_request_package())

    exit_code = main(["dev", "codex-invocation-request", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Codex invocation request draft" in captured.out
    assert "Schema version: codex-invocation-request-draft.v1" in captured.out
    assert "Status: draft" in captured.out
    assert "Handoff ID: codex-handoff-issue-279" in captured.out
    assert "Task ID: task-issue-279-codex-invocation-request" in captured.out
    assert "Source issue number: 279" in captured.out
    assert "Repository: Phoenix-AI-Platform/phoenix-office" in captured.out
    assert "Base branch: main" in captured.out
    assert (
        "Expected PR title: feat: add deterministic Codex invocation request "
        "draft"
    ) in captured.out
    assert "Send performed: no" in captured.out
    assert "Invocation authorized: no" in captured.out
    assert "Worker may merge: no" in captured.out
    assert "Review required: yes" in captured.out
    assert "Rendered prompt:" in captured.out
    assert captured.err == ""


def test_dev_codex_invocation_request_outputs_json_draft(tmp_path, capsys):
    package = _load_valid_request_package()
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["schema_version"] == "codex-invocation-request-draft.v1"
    assert payload["status"] == "draft"
    assert payload["handoff_id"] == "codex-handoff-issue-279"
    assert payload["request_id"] == (
        "codex-invocation-request:codex-handoff-issue-279"
    )
    assert payload["task_id"] == "task-issue-279-codex-invocation-request"
    assert payload["task_title"] == (
        "Add deterministic Codex invocation request draft"
    )
    assert payload["source_issue_number"] == 279
    assert payload["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert payload["base_branch"] == "main"
    assert payload["expected_pr_title"] == package["expected_pr_title"]
    assert payload["declared_changed_files"] == [
        "docs/process/issue-to-codex-handoff.md"
    ]
    assert payload["required_pr_body_headings"] == EXPECTED_HEADINGS
    assert payload["required_repository_validation_commands"] == REQUIRED_COMMANDS
    assert payload["original_reviewed_package_prompt"] == package["prompt"]
    assert payload["invocation_authorized"] is False
    assert payload["send_performed"] is False
    assert payload["worker_may_merge"] is False
    assert payload["review_required"] is True


def test_dev_codex_invocation_request_json_is_byte_identical(tmp_path, capsys):
    path = _write_package(tmp_path, _load_valid_request_package())

    first_exit = main(["dev", "codex-invocation-request", str(path), "--json"])
    first = capsys.readouterr().out
    second_exit = main(["dev", "codex-invocation-request", str(path), "--json"])
    second = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert first == second


def test_dev_codex_invocation_request_prompt_contains_required_sections(
    tmp_path, capsys
):
    package = _load_valid_request_package()
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    rendered = payload["rendered_prompt"]
    assert exit_code == 0
    assert package["prompt"] in rendered
    for section in [
        "## 1. Supervised Pilot Identity",
        "## 2. Source Issue And Handoff",
        "## 3. Repository And Base Branch",
        "## 4. Expected PR Title",
        "## 5. Allowed Changed Files",
        "## 6. Original Reviewed Package Prompt",
        "## 7. Required Validation Commands",
        "## 8. Required PR Body Headings",
        "## 9. Mandatory Execution Boundaries",
        "## 10. External Checks Not Claimed",
    ]:
        assert section in rendered
    for required_text in [
        "Source issue number: 279",
        "Handoff ID: codex-handoff-issue-279",
        "Repository: Phoenix-AI-Platform/phoenix-office",
        "Base branch: main",
        package["expected_pr_title"],
        "- docs/process/issue-to-codex-handoff.md",
        "- one issue, one branch, one PR",
        "- modify only the declared documentation files",
        "- do not broaden scope",
        "- do not use private customer data",
        "- run and report every required validation",
        "- open one PR and stop",
        "- never approve or merge",
        "stop without mutation",
        "duplicate PR detection",
        "branch collision detection",
        "platform budget or usage ceiling enforcement",
        "operator cancellation support",
        "Codex availability",
        "post-PR CI results",
        "assistant review verdict",
    ]:
        assert required_text in rendered


def test_dev_codex_invocation_request_excludes_runtime_and_machine_fields(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("PHOENIX_TEST_SECRET", "do-not-include")
    path = _write_package(tmp_path, _load_valid_request_package())

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    output = captured.out
    payload = json.loads(output)
    assert exit_code == 0
    assert "workspace_path" not in payload
    assert "created_at" not in payload
    assert "updated_at" not in payload
    assert "timestamp" not in output
    assert "C:/tmp/phoenix-office" not in output
    assert "PHOENIX_TEST_SECRET" not in output
    assert "do-not-include" not in output


def test_dev_codex_invocation_request_invalid_static_package_fails_closed(
    tmp_path, capsys
):
    package = _load_valid_request_package()
    package["base_branch"] = "develop"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["invocation_authorized"] is False
    assert payload["send_performed"] is False
    assert payload["worker_may_merge"] is False
    assert payload["review_required"] is True
    assert payload["static_eligible"] is False
    assert payload["input_filename"] == path.name
    assert "path" not in payload
    assert str(path) not in captured.out
    assert "base_branch must be 'main'; got 'develop'" in (
        payload["package_blockers"]
    )
    assert "rendered_prompt" not in payload


def test_dev_codex_invocation_request_missing_file_fails_closed(
    tmp_path, capsys
):
    path = tmp_path / "missing.json"

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["invocation_authorized"] is False
    assert payload["send_performed"] is False
    assert payload["worker_may_merge"] is False
    assert payload["review_required"] is True
    assert payload["input_filename"] == path.name
    assert "path" not in payload
    assert str(path) not in captured.out
    assert payload["package_blockers"] == [
        f"CodexHandoffPackage JSON file does not exist: {path.name}"
    ]
    assert "rendered_prompt" not in payload


def test_dev_codex_invocation_request_malformed_json_fails_closed(
    tmp_path, capsys
):
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")

    exit_code = main(["dev", "codex-invocation-request", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Codex invocation request draft: blocked" in captured.out
    assert f"Input filename: {path.name}" in captured.out
    assert "Invalid JSON" in captured.out
    assert "Rendered prompt: not produced" in captured.out
    assert "Invocation authorized: no" in captured.out
    assert "Send performed: no" in captured.out
    assert "Worker may merge: no" in captured.out
    assert "Review required: yes" in captured.out
    assert str(path) not in captured.out
    assert "## 1. Supervised Pilot Identity" not in captured.out
    assert captured.err == ""


def test_dev_codex_invocation_request_boundary_text_is_non_mutating(
    tmp_path, capsys
):
    path = _write_package(tmp_path, _load_valid_request_package())

    exit_code = main(["dev", "codex-invocation-request", str(path), "--json"])

    captured = capsys.readouterr()
    output = captured.out
    assert exit_code == 0
    assert "do not comment, label, dispatch workflows" in output
    assert "automatically retry, schedule, queue" in output
    assert "open one PR and stop" in output
    assert "never approve or merge" in output
    assert "send_performed" in output
    assert '"send_performed": false' in output
