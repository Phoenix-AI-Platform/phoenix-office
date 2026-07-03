"""Tests for read-only Codex invocation static preflight."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
HANDOFF_EXAMPLE = ROOT / "examples" / "tasks" / "codex_handoff_package.json"
REQUIRED_COMMANDS = [
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
]


def _load_valid_preflight_package() -> dict[str, Any]:
    package = json.loads(HANDOFF_EXAMPLE.read_text(encoding="utf-8"))
    package["expected_pr_title"] = "docs: define supervised pilot boundary"
    package["prompt"] = (
        "Use the verified Phoenix Office checkout only. Update one process "
        "documentation file for Issue #275. Do not invoke Codex from "
        "automation, mutate GitHub, or change runtime behavior."
    )
    package["required_repo_paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    package["task"]["risk_class"] = "docs-only"
    package["task"]["verification_plan"]["commands"] = REQUIRED_COMMANDS
    package["task"]["objective"] = (
        "Document the supervised Codex invocation pilot boundary."
    )
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    return package


def _write_package(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "codex_handoff.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dev_codex_invocation_preflight_text_reports_static_success(
    tmp_path, capsys
):
    path = _write_package(tmp_path, _load_valid_preflight_package())

    exit_code = main(["dev", "codex-invocation-preflight", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Static eligibility: yes" in captured.out
    assert "Handoff ID: codex-handoff-issue-259" in captured.out
    assert "Source issue number: 259" in captured.out
    assert "Repository: Phoenix-AI-Platform/phoenix-office" in captured.out
    assert "Base branch: main" in captured.out
    assert "Declared changed files:" in captured.out
    assert "  - docs/process/issue-to-codex-trigger-evaluation.md" in captured.out
    assert "Static success authorizes invocation: no" in captured.out
    assert "Codex invocation: not authorized" in captured.out
    assert "GitHub access: not performed" in captured.out
    assert "Package blockers:" in captured.out
    assert "  - (none)" in captured.out
    assert "External checks still required:" in captured.out
    assert "duplicate PR detection" in captured.out
    assert "budget or usage ceiling" in captured.out
    assert "Codex availability" in captured.out
    assert captured.err == ""


def test_dev_codex_invocation_preflight_json_reports_static_success(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["static_eligible"] is True
    assert payload["static_success_authorizes_invocation"] is False
    assert payload["invocation_authorized"] is False
    assert payload["package_blockers"] == []
    assert payload["handoff_id"] == package["handoff_id"]
    assert payload["source_issue_number"] == 259
    assert payload["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert payload["base_branch"] == "main"
    assert payload["declared_changed_files"] == [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    assert "duplicate PR detection for the source issue and handoff id" in (
        payload["external_checks_required"]
    )


def test_dev_codex_invocation_preflight_reports_declared_files_from_allowed_resources(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        "docs/development/project_state.md",
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["declared_changed_files"] == [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        "docs/development/project_state.md",
    ]


def test_dev_codex_invocation_preflight_rejects_wrong_repository(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["repository"] = "Phoenix-AI-Platform/other"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert (
        "repository must be 'Phoenix-AI-Platform/phoenix-office'; "
        "got 'Phoenix-AI-Platform/other'"
    ) in payload["package_blockers"]


def test_dev_codex_invocation_preflight_reuses_handoff_validation(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["invocation_authorized"] = True
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["static_eligible"] is False
    assert (
        "invocation_authorized must be JSON boolean False; got True"
        in payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_requires_main_base_branch(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["base_branch"] = "develop"
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "base_branch must be 'main'; got 'develop'" in (
        payload["package_blockers"]
    )


@pytest.mark.parametrize(
    ("permission_name", "unsafe_value"),
    [
        ("destructive", True),
        ("execute", True),
        ("network", True),
        ("destructive", 0),
        ("execute", 1),
        ("network", "false"),
        ("destructive", None),
    ],
)
def test_dev_codex_invocation_preflight_rejects_unsafe_task_permissions(
    tmp_path, capsys, permission_name, unsafe_value
):
    package = _load_valid_preflight_package()
    if unsafe_value is None:
        del package["task"]["permissions"][permission_name]
    else:
        package["task"]["permissions"][permission_name] = unsafe_value
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert any(
        f"task.permissions.{permission_name} must be JSON boolean False"
        in blocker
        for blocker in payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_missing_permissions_object(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    del package["task"]["permissions"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "task.permissions must be an object" in payload["package_blockers"]


def test_dev_codex_invocation_preflight_rejects_non_docs_paths(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = ["src/phoenix_office/cli.py"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert any(
        "required_repo_paths must contain only safe repository-relative "
        "Markdown files" in blocker
        for blocker in payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_zero_declared_files(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = []
    package["task"]["allowed_resources"]["paths"] = []
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "required_repo_paths must contain at least 1 path" in (
        payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_enforces_three_file_cap(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = [
        "docs/process/a.md",
        "docs/process/b.md",
        "docs/development/c.md",
        "docs/development/d.md",
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "required_repo_paths must contain no more than 3 paths" in (
        payload["package_blockers"]
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "docs/process/../../src/phoenix_office/cli.md",
        "docs/process/./pilot.md",
        "/docs/process/pilot.md",
        "C:/tmp/phoenix-office/docs/process/pilot.md",
        "docs/process/pilot.txt",
        "docs/other/pilot.md",
    ],
)
def test_dev_codex_invocation_preflight_rejects_traversal_or_ambiguous_paths(
    tmp_path, capsys, unsafe_path
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = [unsafe_path]
    package["task"]["allowed_resources"]["paths"] = [unsafe_path]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert any(
        "required_repo_paths must contain only safe repository-relative "
        "Markdown files" in blocker
        for blocker in payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_requires_required_paths_in_allowed_resources(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/different.md"
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert (
        "required_repo_paths entries must also appear in "
        "task.allowed_resources.paths: "
        "'docs/process/issue-to-codex-trigger-evaluation.md'"
    ) in payload["package_blockers"]


def test_dev_codex_invocation_preflight_requires_allowed_resources_paths(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    del package["task"]["allowed_resources"]["paths"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "task.allowed_resources.paths must be a list of strings" in (
        payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_extra_code_allowed_path(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        "src/phoenix_office/cli.py",
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert any(
        "task.allowed_resources.paths must contain only safe "
        "repository-relative Markdown files" in blocker
        for blocker in payload["package_blockers"]
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "docs/process/../../src/phoenix_office/cli.md",
        "docs/process/./pilot.md",
        "/docs/process/pilot.md",
        "C:/tmp/phoenix-office/docs/process/pilot.md",
        "docs/process/pilot.txt",
        "docs/other/pilot.md",
    ],
)
def test_dev_codex_invocation_preflight_rejects_unsafe_allowed_paths(
    tmp_path, capsys, unsafe_path
):
    package = _load_valid_preflight_package()
    package["required_repo_paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        unsafe_path,
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert any(
        "task.allowed_resources.paths must contain only safe "
        "repository-relative Markdown files" in blocker
        for blocker in payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_more_than_three_allowed_paths(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/a.md",
        "docs/process/b.md",
        "docs/development/c.md",
        "docs/development/d.md",
    ]
    package["required_repo_paths"] = ["docs/process/a.md"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "task.allowed_resources.paths must contain no more than 3 paths" in (
        payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_non_string_allowed_path(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        7,
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "task.allowed_resources.paths must contain only strings" in (
        payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_rejects_duplicate_allowed_paths(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md",
        "docs/process/issue-to-codex-trigger-evaluation.md",
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert "task.allowed_resources.paths must be unique" in (
        payload["package_blockers"]
    )


def test_dev_codex_invocation_preflight_requires_repository_validation(
    tmp_path, capsys
):
    package = _load_valid_preflight_package()
    package["task"]["verification_plan"]["commands"] = ["git diff --check"]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert (
        "task.verification_plan.commands must include "
        "'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp "
        ".pytest_tmp'"
    ) in payload["package_blockers"]
    assert (
        "task.verification_plan.commands must include "
        "'python -m ruff check . --no-cache'"
    ) in payload["package_blockers"]


@pytest.mark.parametrize(
    "missing_heading",
    [
        "Summary",
        "Scope",
        "Changed files",
        "Out-of-scope confirmation",
        "Validation performed",
        "Risks",
    ],
)
def test_dev_codex_invocation_preflight_requires_each_pr_heading(
    tmp_path, capsys, missing_heading
):
    package = _load_valid_preflight_package()
    package["required_pr_body_headings"] = [
        heading
        for heading in package["required_pr_body_headings"]
        if heading != missing_heading
    ]
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert (
        f"required_pr_body_headings must include {missing_heading!r}"
        in payload["package_blockers"]
    )


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"kind": "github_issue", "uri": ""},
        {
            "kind": "github_issue",
            "uri": "https://github.com/Phoenix-AI-Platform/other/issues/259",
        },
        {
            "kind": "manual",
            "uri": "https://github.com/Phoenix-AI-Platform/phoenix-office/issues/259",
        },
    ],
)
def test_dev_codex_invocation_preflight_rejects_missing_or_foreign_issue_source(
    tmp_path, capsys, source
):
    package = _load_valid_preflight_package()
    package["task"]["source"] = source
    path = _write_package(tmp_path, package)

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["source_issue_number"] is None
    assert payload["package_blockers"]


def test_dev_codex_invocation_preflight_missing_file_json_reports_blocker(
    tmp_path, capsys
):
    path = tmp_path / "missing.json"

    exit_code = main(["dev", "codex-invocation-preflight", str(path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert captured.err == ""
    assert payload["static_eligible"] is False
    assert payload["package_blockers"] == [
        f"CodexHandoffPackage JSON file does not exist: {path}"
    ]
    assert payload["static_success_authorizes_invocation"] is False
