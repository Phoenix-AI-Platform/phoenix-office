"""Tests for supervised Codex pilot authorization packet inspection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import phoenix_office.cli as cli
from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
HANDOFF_EXAMPLE = ROOT / "examples" / "tasks" / "codex_handoff_package.json"
REQUIRED_COMMANDS = [
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
]
SUPPORTED_HELP = """
Usage: codex exec [OPTIONS]

Run Codex non-interactively.
Read prompt from stdin or prompt from -
  --ephemeral
  --sandbox <MODE>
  --cd <DIR>
  -C <DIR>
  --json
  --output-last-message <FILE>
  -o <FILE>
  --token-budget <TOKENS>
"""
CONTROL_REVIEWERS = {
    "authentication_runner_access": "human_operator",
    "per_run_budget_ceiling": "human_operator_and_assistant_reviewer",
    "operator_cancellation_timeout": "human_operator",
    "github_branch_creation_permission": "human_operator",
    "github_pr_creation_permission": "human_operator_and_assistant_reviewer",
    "codex_cannot_approve_or_merge": "assistant_reviewer",
    "duplicate_active_pr_detection": "assistant_reviewer",
    "branch_collision_detection": "assistant_reviewer",
    "codex_task_time_availability": "human_operator",
    "final_ci_requirement": "assistant_reviewer",
    "assistant_architecture_review": "assistant_reviewer",
}
UNSAFE_FRAGMENTS = [
    "C:/Users/private-name",
    "/home/private-name",
    "https://example.com/secret",
    "sk-proj-super-secret",
    "token-value",
    "password=secret",
    "AppData",
    "PRIVATE CUSTOMER NAME",
]


def _completed(argv: list[str], stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _install_runtime_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version_stdout: str = "codex-cli 1.2.3\n",
    help_stdout: str = SUPPORTED_HELP,
    executable_found: bool = True,
    timeout_argv: list[str] | None = None,
) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: "C:/safe/codex.exe"
        if name == "codex" and executable_found
        else None,
    )

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if timeout_argv is not None and list(argv) == timeout_argv:
            raise subprocess.TimeoutExpired(argv, 5)
        if list(argv) == ["codex", "--version"]:
            return _completed(list(argv), version_stdout)
        if list(argv) == ["codex", "exec", "--help"]:
            return _completed(list(argv), help_stdout)
        raise AssertionError(f"Unexpected argv: {argv!r}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


def _valid_handoff_package() -> dict[str, Any]:
    package = json.loads(HANDOFF_EXAMPLE.read_text(encoding="utf-8"))
    package["expected_pr_title"] = "docs: update supervised Codex pilot documentation"
    package["prompt"] = "Reviewed prompt text that must never appear in reports."
    package["required_repo_paths"] = [
        "docs/process/supervised-codex-pilot-authorization.md"
    ]
    package["task"]["risk_class"] = "docs-only"
    package["task"]["objective"] = "Document the supervised Codex pilot authorization packet."
    package["task"]["verification_plan"]["commands"] = REQUIRED_COMMANDS
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/supervised-codex-pilot-authorization.md"
    ]
    return package


def _valid_evidence_package(handoff_id: str = "codex-handoff-issue-259") -> dict[str, Any]:
    return {
        "schema_version": "codex-pilot-evidence.v1",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "handoff_id": handoff_id,
        "pilot_ready": False,
        "invocation_authorized": False,
        "controls": [
            {
                "control_id": control_id,
                "status": "verified",
                "evidence_ref": f"{control_id}-evidence",
                "reviewer_role": reviewer_role,
            }
            for control_id, reviewer_role in CONTROL_REVIEWERS.items()
        ],
    }


def _valid_authorization_packet() -> dict[str, Any]:
    return {
        "schema_version": "codex-pilot-authorization.v1",
        "authorization_id": "pilot-auth-issue-292",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "decision_state": "human_authorized_for_one_run",
        "authorizer_role": "human_operator",
        "base_commit_sha": "0" * 40,
        "handoff_path": "handoff.json",
        "evidence_path": "evidence.json",
        "handoff_id": "codex-handoff-issue-259",
        "objective": "Document the supervised Codex pilot authorization packet.",
        "allowed_paths": [
            "docs/process/supervised-codex-pilot-authorization.md"
        ],
        "expected_pr_title": "docs: update supervised Codex pilot documentation",
        "branch_name": "codex/approved-supervised-pilot",
        "validation_commands": REQUIRED_COMMANDS,
        "budget_metric": "tokens",
        "budget_ceiling": 50000,
        "budget_enforcement_ref": "budget-control-reviewed",
        "timeout_seconds": 1800,
        "cancellation_ref": "operator-cancel-reviewed",
        "authentication_runner_ref": "runner-access-reviewed",
        "branch_permission_ref": "branch-permission-reviewed",
        "pr_permission_ref": "pr-permission-reviewed",
        "duplicate_pr_check_ref": "duplicate-pr-check-reviewed",
        "branch_collision_check_ref": "branch-collision-check-reviewed",
        "codex_no_approve_merge_ref": "no-approve-merge-reviewed",
        "final_ci_required": True,
        "assistant_review_required": True,
        "worker_may_approve": False,
        "worker_may_merge": False,
        "one_invocation_only": True,
        "retry_authorized": False,
        "background_execution_authorized": False,
    }


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_all(
    tmp_path: Path,
    *,
    handoff: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    authorization: dict[str, Any] | None = None,
    authorization_filename: str = "authorization.json",
) -> tuple[Path, Path, Path]:
    handoff_path = _write_json(
        tmp_path / "handoff.json",
        handoff if handoff is not None else _valid_handoff_package(),
    )
    evidence_path = _write_json(
        tmp_path / "evidence.json",
        evidence if evidence is not None else _valid_evidence_package(),
    )
    authorization_path = _write_json(
        tmp_path / authorization_filename,
        authorization if authorization is not None else _valid_authorization_packet(),
    )
    return handoff_path, evidence_path, authorization_path


def _run_json(
    handoff_path: Path,
    evidence_path: Path,
    authorization_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, Any], str]:
    exit_code = main(
        [
            "dev",
            "codex-pilot-authorization",
            str(handoff_path),
            str(evidence_path),
            str(authorization_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out), captured.out


def _run_text(
    handoff_path: Path,
    evidence_path: Path,
    authorization_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    exit_code = main(
        [
            "dev",
            "codex-pilot-authorization",
            str(handoff_path),
            str(evidence_path),
            str(authorization_path),
        ]
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, captured.out


def _assert_no_unsafe_output(output: str) -> None:
    for fragment in UNSAFE_FRAGMENTS:
        assert fragment not in output
    for fragment in ["Traceback", "Reviewed prompt text", "evidence-ref"]:
        assert fragment not in output


def _assert_authorization_structural_failure(report: dict[str, Any]) -> None:
    assert report["authorization_structural_valid"] is False
    assert report["authorization_binding_passed"] is False
    assert report["authorization_packet_valid_for_one_attempt"] is False


def _assert_unsafe_fragments_do_not_leak(
    outputs: list[str], fragments: list[str]
) -> None:
    for output in outputs:
        for fragment in fragments:
            assert fragment not in output


def _unsafe_fragments(value: str) -> list[str]:
    encoded = json.dumps(value)[1:-1]
    candidates = [
        value,
        encoded,
        "private-name",
        "C:/Users",
        "/home",
        "AppData",
        "PRIVATE CUSTOMER NAME",
        "approved\\tpilot",
        "approved pilot\\rhidden",
        "approved pilot\\nhidden",
        "reviewed path",
        "reviewed\\tpath",
        "Users/private-name",
    ]
    return sorted(
        {fragment for fragment in candidates if fragment and fragment in f"{value} {encoded}"}
    )


def test_codex_pilot_authorization_success_json_text_and_determinism(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)

    exit_code, report, first_json = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    second_exit, second_report, second_json = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 0
    assert second_exit == 0
    assert text_exit == 0
    assert first_json == second_json
    assert report == second_report
    assert report["schema_version"] == "codex-pilot-authorization.v1"
    assert report["command"] == "dev codex-pilot-authorization"
    assert report["authorization_id"] == "pilot-auth-issue-292"
    assert report["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert report["pilot_kind"] == "docs-only-supervised"
    assert report["decision_state"] == "human_authorized_for_one_run"
    assert report["authorizer_role"] == "human_operator"
    assert report["base_commit_sha"] == "0" * 40
    assert report["handoff_id"] == "codex-handoff-issue-259"
    assert report["allowed_paths"] == [
        "docs/process/supervised-codex-pilot-authorization.md"
    ]
    assert report["expected_pr_title"] == "docs: update supervised Codex pilot documentation"
    assert report["branch_name"] == "codex/approved-supervised-pilot"
    assert report["budget_metric"] == "tokens"
    assert report["budget_ceiling"] == 50000
    assert report["timeout_seconds"] == 1800
    assert report["composite_preflight_passed"] is True
    assert report["authorization_structural_valid"] is True
    assert report["authorization_binding_passed"] is True
    assert report["authorization_packet_valid_for_one_attempt"] is True
    assert report["pilot_ready"] is False
    assert report["invocation_performed"] is False
    assert report["prompt_submitted"] is False
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["mutation_performed"] is False
    assert report["branch_created"] is False
    assert report["pull_request_created"] is False
    assert "Invocation performed: no" in text_output
    assert "Authorization packet valid for one attempt: yes" in text_output
    assert calls == [
        ["codex", "--version"],
        ["codex", "exec", "--help"],
        ["codex", "--version"],
        ["codex", "exec", "--help"],
        ["codex", "--version"],
        ["codex", "exec", "--help"],
    ]


@pytest.mark.parametrize(
    ("runtime_kwargs", "expected"),
    [
        ({"executable_found": False}, "composite runtime preflight blocked"),
        ({"timeout_argv": ["codex", "--version"]}, "composite runtime preflight blocked"),
        ({"help_stdout": ""}, "composite runtime preflight blocked"),
    ],
)
def test_codex_pilot_authorization_composite_runtime_failures_are_sanitized(
    tmp_path, capsys, monkeypatch, runtime_kwargs, expected
):
    _install_runtime_mocks(monkeypatch, **runtime_kwargs)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert report["composite_preflight_passed"] is False
    assert report["authorization_packet_valid_for_one_attempt"] is False
    assert expected in report["blockers_by_source"]["composite_preflight"]
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize(
    ("update", "expected_source", "expected"),
    [
        (
            {"base_branch": "feature"},
            "composite_preflight",
            "composite handoff preflight blocked",
        ),
        (
            {"handoff_id": "other-handoff"},
            "authorization_binding",
            "authorization handoff id does not match",
        ),
    ],
)
def test_codex_pilot_authorization_invalid_handoff_or_binding_fails_closed(
    tmp_path, capsys, monkeypatch, update, expected_source, expected
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    handoff.update(update)
    evidence = _valid_evidence_package(update.get("handoff_id", "codex-handoff-issue-259"))
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, handoff=handoff, evidence=evidence
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert expected in report["blockers_by_source"][expected_source]
    _assert_no_unsafe_output(output)


def test_codex_pilot_authorization_incomplete_evidence_fails_closed(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    evidence = _valid_evidence_package()
    evidence["controls"][0]["status"] = "blocked"
    evidence["controls"][0]["evidence_ref"] = ""
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, evidence=evidence
    )

    exit_code, report, _output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert report["composite_preflight_passed"] is False
    assert "composite evidence preflight blocked" in (
        report["blockers_by_source"]["composite_preflight"]
    )


def test_codex_pilot_authorization_unsafe_input_filename_fails_closed(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization_filename="token-value.json"
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert report["authorization_filename"] is None
    assert "authorization input filename is unsafe" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    assert "token-value" not in output


@pytest.mark.parametrize(
    ("path_factory", "expected"),
    [
        (lambda tmp_path: tmp_path / "missing.json", "authorization package is missing"),
        (lambda tmp_path: tmp_path, "authorization package is unreadable"),
    ],
)
def test_codex_pilot_authorization_missing_or_unreadable_authorization_file(
    tmp_path, capsys, monkeypatch, path_factory, expected
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, _authorization_path = _write_all(tmp_path)
    bad_path = path_factory(tmp_path)

    exit_code, report, output = _run_json(handoff_path, evidence_path, bad_path, capsys)

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert expected in report["blockers_by_source"]["authorization_structural"]
    assert str(tmp_path) not in output
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("{not-json-password=secret", "authorization package is malformed"),
        ("[]", "authorization package root must be an object"),
    ],
)
def test_codex_pilot_authorization_malformed_or_non_object_json(
    tmp_path, capsys, monkeypatch, content, expected
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)
    authorization_path.write_text(content, encoding="utf-8")

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert expected in report["blockers_by_source"]["authorization_structural"]
    assert "password=secret" not in output
    assert "Traceback" not in output


@pytest.mark.parametrize("field", sorted(cli.CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS))
def test_codex_pilot_authorization_missing_required_fields_fail_closed(
    tmp_path, capsys, monkeypatch, field
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization.pop(field)
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, _output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert "authorization package is missing required fields" in (
        report["blockers_by_source"]["authorization_structural"]
    )


def test_codex_pilot_authorization_unknown_fields_do_not_leak_names(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization["password=secret"] = "PRIVATE CUSTOMER NAME"
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert "authorization package contains unknown fields" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "wrong", "authorization schema_version is invalid"),
        ("repository", "other/repo", "authorization repository is invalid"),
        ("pilot_kind", "runtime", "authorization pilot_kind is invalid"),
        ("decision_state", "blocked", "authorization decision_state is invalid"),
        ("authorizer_role", "assistant", "authorization authorizer_role is invalid"),
        ("base_commit_sha", "A" * 40, "authorization base_commit_sha is invalid"),
        ("base_commit_sha", "0" * 39, "authorization base_commit_sha is invalid"),
        ("base_commit_sha", "0" * 41, "authorization base_commit_sha is invalid"),
        ("base_commit_sha", "g" * 40, "authorization base_commit_sha is invalid"),
        ("base_commit_sha", " 000", "authorization base_commit_sha is invalid"),
        (
            "handoff_path",
            "C:/Users/private-name/handoff.json",
            "authorization handoff_path is invalid",
        ),
        (
            "evidence_path",
            "https://example.com/secret.json",
            "authorization evidence_path is invalid",
        ),
        ("objective", "Update runtime code.", "authorization objective is invalid"),
        ("expected_pr_title", "feat: runtime", "authorization expected_pr_title is invalid"),
        ("branch_name", "feature/test", "authorization branch_name is invalid"),
        ("branch_name", "codex/bad..branch", "authorization branch_name is invalid"),
        ("branch_name", "codex/bad@{branch", "authorization branch_name is invalid"),
        ("branch_name", "codex/bad branch", "authorization branch_name is invalid"),
        ("branch_name", "codex/bad/", "authorization branch_name is invalid"),
        ("budget_metric", "cost", "authorization budget_metric is invalid"),
        ("budget_ceiling", 0, "authorization budget is invalid"),
        ("budget_ceiling", True, "authorization budget is invalid"),
        ("budget_ceiling", 1.5, "authorization budget is invalid"),
        ("budget_ceiling", "100", "authorization budget is invalid"),
        ("budget_ceiling", None, "authorization budget is invalid"),
        ("budget_ceiling", 1_000_001, "authorization budget is invalid"),
        ("timeout_seconds", 0, "authorization timeout is invalid"),
        ("timeout_seconds", True, "authorization timeout is invalid"),
        ("timeout_seconds", 1.5, "authorization timeout is invalid"),
        ("timeout_seconds", "1800", "authorization timeout is invalid"),
        ("timeout_seconds", None, "authorization timeout is invalid"),
        ("timeout_seconds", 7201, "authorization timeout is invalid"),
    ],
)
def test_codex_pilot_authorization_structural_field_failures(
    tmp_path, capsys, monkeypatch, field, value, expected
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization[field] = value
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert expected in report["blockers_by_source"]["authorization_structural"]
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize(
    "allowed_paths",
    [
        [],
        [
            "docs/process/one.md",
            "docs/process/two.md",
            "docs/process/three.md",
            "docs/process/four.md",
        ],
        ["docs/process/one.md", "docs/process/one.md"],
        ["docs/process/one.md", 7],
        ["docs/process/one.txt"],
        ["docs/development/project_state.md"],
        ["docs/process/../secret.md"],
        ["C:/Users/private-name/file.md"],
        ["docs\\process\\file.md"],
        ["https://example.com/secret.md"],
        ["src/phoenix_office/cli.py"],
        ["tests/test_cli.py"],
        [".github/workflows/tests.yml"],
        ["examples/tasks/example.json"],
        ["templates/template.docx"],
    ],
)
def test_codex_pilot_authorization_allowed_path_failures(
    tmp_path, capsys, monkeypatch, allowed_paths
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization["allowed_paths"] = allowed_paths
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert "authorization allowed paths are invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize("field", cli.CODEX_PILOT_AUTHORIZATION_REFERENCE_FIELDS)
@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        0,
        True,
        [],
        {},
        ".",
        "..",
        "https://example.com/secret",
        "a/b",
        "sk-proj-super-secret",
        "token-value",
        "secret-value",
        "password=secret",
        "a" * 81,
    ],
)
def test_codex_pilot_authorization_reference_failures_are_sanitized(
    tmp_path, capsys, monkeypatch, field, value
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization[field] = value
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert f"authorization {field} is invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_no_unsafe_output(output)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("final_ci_required", False, "authorization final_ci_required must be JSON boolean true"),
        (
            "assistant_review_required",
            False,
            "authorization assistant_review_required must be JSON boolean true",
        ),
        (
            "one_invocation_only",
            False,
            "authorization one_invocation_only must be JSON boolean true",
        ),
        (
            "worker_may_approve",
            True,
            "authorization worker_may_approve must be JSON boolean false",
        ),
        ("worker_may_merge", True, "authorization worker_may_merge must be JSON boolean false"),
        ("retry_authorized", True, "authorization retry_authorized must be JSON boolean false"),
        (
            "background_execution_authorized",
            True,
            "authorization background_execution_authorized must be JSON boolean false",
        ),
        ("final_ci_required", 1, "authorization final_ci_required must be JSON boolean true"),
        ("worker_may_merge", 0, "authorization worker_may_merge must be JSON boolean false"),
    ],
)
def test_codex_pilot_authorization_safety_flag_inversions_fail(
    tmp_path, capsys, monkeypatch, field, value, expected
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization[field] = value
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, _output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    _assert_authorization_structural_failure(report)
    assert expected in report["blockers_by_source"]["authorization_structural"]


@pytest.mark.parametrize(
    "unsafe_objective",
    [
        "Document /home/private-name/config.",
        "Document C:/Users/private-name/config.",
        "Document AppData configuration.",
        "Document PRIVATE CUSTOMER NAME records.",
        "Document approved\tpilot.",
        "Document approved pilot.\rhidden",
        "Document approved pilot.\nhidden",
    ],
)
def test_codex_pilot_authorization_matching_unsafe_objective_is_structural_failure(
    tmp_path, capsys, monkeypatch, unsafe_objective
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    handoff["task"]["objective"] = unsafe_objective
    authorization = _valid_authorization_packet()
    authorization["objective"] = unsafe_objective
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, handoff=handoff, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    _assert_authorization_structural_failure(report)
    assert "authorization objective is invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_unsafe_fragments_do_not_leak(
        [json_output, text_output], _unsafe_fragments(unsafe_objective)
    )


@pytest.mark.parametrize(
    "unsafe_title",
    [
        "docs: PRIVATE CUSTOMER NAME /home/private-name",
        "docs: C:/Users/private-name",
        "docs: AppData configuration",
        "docs: approved\tpilot",
        "docs: approved pilot\rhidden",
    ],
)
def test_codex_pilot_authorization_matching_unsafe_pr_title_is_structural_failure(
    tmp_path, capsys, monkeypatch, unsafe_title
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    handoff["expected_pr_title"] = unsafe_title
    authorization = _valid_authorization_packet()
    authorization["expected_pr_title"] = unsafe_title
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, handoff=handoff, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    _assert_authorization_structural_failure(report)
    assert "authorization expected_pr_title is invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_unsafe_fragments_do_not_leak(
        [json_output, text_output], _unsafe_fragments(unsafe_title)
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "docs/process/private name.md",
        "docs/process/file\tname.md",
        "docs/process/file\rname.md",
        "docs/process//file.md",
        "docs/process/./file.md",
        "docs/process/../file.md",
        "docs/process/AppData.md",
        "docs/process/PRIVATE CUSTOMER NAME.md",
    ],
)
def test_codex_pilot_authorization_matching_unsafe_allowed_path_is_structural_failure(
    tmp_path, capsys, monkeypatch, unsafe_path
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    handoff["required_repo_paths"] = [unsafe_path]
    handoff["task"]["allowed_resources"]["paths"] = [unsafe_path]
    authorization = _valid_authorization_packet()
    authorization["allowed_paths"] = [unsafe_path]
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, handoff=handoff, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    _assert_authorization_structural_failure(report)
    assert "authorization allowed paths are invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_unsafe_fragments_do_not_leak(
        [json_output, text_output], _unsafe_fragments(unsafe_path)
    )


@pytest.mark.parametrize(
    ("field", "unsafe_path"),
    [
        ("handoff_path", "reviewed path/handoff.json"),
        ("handoff_path", "reviewed\tpath/handoff.json"),
        ("handoff_path", "AppData/handoff.json"),
        ("handoff_path", "Users/private-name/handoff.json"),
        ("evidence_path", "reviewed path/evidence.json"),
        ("evidence_path", "reviewed\tpath/evidence.json"),
        ("evidence_path", "AppData/evidence.json"),
        ("evidence_path", "Users/private-name/evidence.json"),
    ],
)
def test_codex_pilot_authorization_unsafe_declared_json_paths_are_structural_failure(
    tmp_path, capsys, monkeypatch, field, unsafe_path
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization[field] = unsafe_path
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    _assert_authorization_structural_failure(report)
    assert f"authorization {field} is invalid" in (
        report["blockers_by_source"]["authorization_structural"]
    )
    _assert_unsafe_fragments_do_not_leak(
        [json_output, text_output], _unsafe_fragments(unsafe_path)
    )

@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("handoff_path", "other-handoff.json", "authorization handoff path does not match input"),
        (
            "evidence_path",
            "other-evidence.json",
            "authorization evidence path does not match input",
        ),
        ("handoff_id", "other-handoff", "authorization handoff id does not match"),
        (
            "objective",
            "Document another supervised Codex pilot authorization packet.",
            "authorization objective does not match handoff",
        ),
        (
            "allowed_paths",
            ["docs/process/other.md"],
            "authorization allowed paths do not match handoff",
        ),
        (
            "expected_pr_title",
            "docs: another supervised Codex pilot documentation",
            "authorization expected PR title does not match handoff",
        ),
        (
            "validation_commands",
            list(reversed(REQUIRED_COMMANDS)),
            "authorization validation commands are invalid",
        ),
    ],
)
def test_codex_pilot_authorization_binding_mismatches_are_not_structural(
    tmp_path, capsys, monkeypatch, field, value, expected
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization[field] = value
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, _output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    if expected == "authorization validation commands are invalid":
        assert expected in report["blockers_by_source"]["authorization_structural"]
    else:
        assert report["authorization_structural_valid"] is True
        assert expected in report["blockers_by_source"]["authorization_binding"]
    assert report["authorization_packet_valid_for_one_attempt"] is False


def test_codex_pilot_authorization_leakage_prevention(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(
        monkeypatch,
        version_stdout="C:/Users/private-name/codex\ncodex-cli 1.2.3\n",
    )
    authorization = _valid_authorization_packet()
    authorization["objective"] = "PRIVATE CUSTOMER NAME https://example.com/secret"
    authorization["branch_name"] = "codex/token-value"
    authorization["expected_pr_title"] = "docs: password=secret"
    authorization["authorization_id"] = "sk-proj-super-secret"
    handoff = _valid_handoff_package()
    handoff["prompt"] = "Reviewed prompt text with token-value"
    evidence = _valid_evidence_package()
    evidence["controls"][0]["evidence_ref"] = "secret-evidence-ref"
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path,
        handoff=handoff,
        evidence=evidence,
        authorization=authorization,
    )

    exit_code, _report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    _assert_no_unsafe_output(json_output)
    _assert_no_unsafe_output(text_output)


def test_codex_pilot_authorization_no_behavior_expansion(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)

    exit_code, report, _output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 0
    assert calls == [["codex", "--version"], ["codex", "exec", "--help"]]
    assert report["invocation_performed"] is False
    assert report["prompt_submitted"] is False
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["branch_created"] is False
    assert report["pull_request_created"] is False
    assert report["mutation_performed"] is False
