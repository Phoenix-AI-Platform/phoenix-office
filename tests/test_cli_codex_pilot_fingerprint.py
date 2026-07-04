"""Tests for supervised Codex pilot authorization fingerprint inspection."""

from __future__ import annotations

import hashlib
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
FALSE_FLAGS = [
    "authorization_claimed",
    "authorization_consumed",
    "pilot_ready",
    "invocation_performed",
    "prompt_submitted",
    "github_access_performed",
    "network_access_performed",
    "mutation_performed",
    "branch_created",
    "pull_request_created",
]
UNSAFE_FRAGMENTS = [
    "C:/Users/private-name",
    "/home/private-name",
    "https://example.com/secret",
    "sk-proj-super-secret",
    "token-value",
    "password=secret",
    "AppData",
    "PRIVATE CUSTOMER NAME",
    "Reviewed prompt text",
    "authentication_runner_access-evidence",
]


def _completed(argv: list[str], stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _install_runtime_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
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
            return _completed(list(argv), "codex-cli 1.2.3\n")
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


def _valid_evidence_package() -> dict[str, Any]:
    return {
        "schema_version": "codex-pilot-evidence.v1",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "handoff_id": "codex-handoff-issue-259",
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
            "codex-pilot-fingerprint",
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
            "codex-pilot-fingerprint",
            str(handoff_path),
            str(evidence_path),
            str(authorization_path),
        ]
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, captured.out


def _expected_fingerprint(package: dict[str, Any]) -> str:
    payload = {
        field_name: package[field_name]
        for field_name in cli.CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest_input = (
        cli.CODEX_PILOT_AUTHORIZATION_FINGERPRINT_PREFIX.encode("utf-8")
        + canonical.encode("utf-8")
    )
    return hashlib.sha256(digest_input).hexdigest()


def _assert_false_flags(report: dict[str, Any]) -> None:
    for field_name in FALSE_FLAGS:
        assert report[field_name] is False


def _assert_no_leakage(output: str) -> None:
    for fragment in UNSAFE_FRAGMENTS:
        assert fragment not in output
    assert "Traceback" not in output


def test_codex_pilot_fingerprint_success_json_text_and_determinism(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

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
    assert report["schema_version"] == "codex-pilot-fingerprint.v1"
    assert report["command"] == "dev codex-pilot-fingerprint"
    assert report["fingerprint_schema_version"] == (
        "phoenix-codex-authorization-fingerprint.v1"
    )
    assert report["authorization_inspection_passed"] is True
    assert report["authorization_fingerprint_valid"] is True
    assert report["authorization_fingerprint"] == _expected_fingerprint(
        authorization
    )
    assert len(report["authorization_fingerprint"]) == 64
    assert report["authorization_fingerprint"] == (
        report["authorization_fingerprint"].lower()
    )
    assert report["authorization_id"] == "pilot-auth-issue-292"
    assert report["handoff_id"] == "codex-handoff-issue-259"
    _assert_false_flags(report)
    assert "Authorization fingerprint valid: yes" in text_output
    assert "Authorization claimed: no" in text_output
    assert "Authorization consumed: no" in text_output
    assert calls == [
        ["codex", "--version"],
        ["codex", "exec", "--help"],
        ["codex", "--version"],
        ["codex", "exec", "--help"],
        ["codex", "--version"],
        ["codex", "exec", "--help"],
    ]
    _assert_no_leakage(first_json)
    assert "canonical" not in first_json.lower()


def test_codex_pilot_fingerprint_matches_contract_illustrative_payload() -> None:
    payload = {
        "allowed_paths": ["docs/process/approved-pilot.md"],
        "assistant_review_required": True,
        "authentication_runner_ref": "runner-access-reviewed",
        "authorization_id": "pilot-auth-example",
        "authorizer_role": "human_operator",
        "background_execution_authorized": False,
        "base_commit_sha": "0" * 40,
        "branch_collision_check_ref": "branch-collision-reviewed",
        "branch_name": "codex/approved-pilot",
        "branch_permission_ref": "branch-permission-reviewed",
        "budget_ceiling": 50000,
        "budget_enforcement_ref": "budget-control-reviewed",
        "budget_metric": "tokens",
        "cancellation_ref": "operator-cancel-reviewed",
        "codex_no_approve_merge_ref": "no-approve-merge-reviewed",
        "decision_state": "human_authorized_for_one_run",
        "duplicate_pr_check_ref": "duplicate-pr-reviewed",
        "evidence_path": "reviewed/evidence.json",
        "expected_pr_title": "docs: update approved pilot documentation",
        "final_ci_required": True,
        "handoff_id": "codex-handoff-example",
        "handoff_path": "reviewed/handoff.json",
        "objective": "Document the approved supervised pilot boundary.",
        "one_invocation_only": True,
        "pilot_kind": "docs-only-supervised",
        "pr_permission_ref": "pr-permission-reviewed",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "retry_authorized": False,
        "schema_version": "codex-pilot-authorization.v1",
        "timeout_seconds": 1800,
        "validation_commands": REQUIRED_COMMANDS,
        "worker_may_approve": False,
        "worker_may_merge": False,
    }

    assert cli._codex_pilot_authorization_fingerprint(payload) == (
        "6bdd92a90bd8443eecace70e88134c68"
        "e6ebf1a0490c4d986b38086a845f4e0d"
    )


def test_codex_pilot_fingerprint_changes_for_each_canonical_field() -> None:
    package = _valid_authorization_packet()
    baseline = cli._codex_pilot_authorization_fingerprint(package)

    for field_name in cli.CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS:
        mutated = dict(package)
        value = mutated[field_name]
        if isinstance(value, bool):
            mutated[field_name] = not value
        elif type(value) is int:
            mutated[field_name] = value + 1
        elif isinstance(value, list):
            mutated[field_name] = [*value, value[-1]]
        else:
            mutated[field_name] = f"{value}-changed"

        assert cli._codex_pilot_authorization_fingerprint(mutated) != baseline


def test_codex_pilot_fingerprint_ignores_object_insertion_order() -> None:
    package = _valid_authorization_packet()
    reordered = {
        field_name: package[field_name]
        for field_name in reversed(cli.CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS)
    }

    assert cli._codex_pilot_authorization_fingerprint(package) == (
        cli._codex_pilot_authorization_fingerprint(reordered)
    )


def test_codex_pilot_fingerprint_preserves_list_order() -> None:
    package = _valid_authorization_packet()
    package["allowed_paths"] = ["docs/process/a.md", "docs/process/b.md"]
    reordered = dict(package)
    reordered["allowed_paths"] = ["docs/process/b.md", "docs/process/a.md"]

    assert cli._codex_pilot_authorization_fingerprint(package) != (
        cli._codex_pilot_authorization_fingerprint(reordered)
    )


def test_codex_pilot_fingerprint_preserves_validation_commands_order() -> None:
    package = _valid_authorization_packet()
    reordered = dict(package)
    reordered["validation_commands"] = list(reversed(REQUIRED_COMMANDS))

    assert cli._codex_pilot_authorization_fingerprint(package) != (
        cli._codex_pilot_authorization_fingerprint(reordered)
    )


def test_codex_pilot_fingerprint_command_rejects_reordered_validation_commands(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization["validation_commands"] = list(reversed(REQUIRED_COMMANDS))
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert report["authorization_inspection_passed"] is False
    assert report["authorization_fingerprint_valid"] is False
    assert report["authorization_fingerprint"] is None
    assert "authorization structural blocked" in (
        report["blockers_by_source"]["authorization"]
    )
    assert "canonical" not in json_output.lower()


def test_codex_pilot_fingerprint_uses_the_authorization_object_that_was_inspected(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    inspected_authorization = _valid_authorization_packet()
    replacement_authorization = _valid_authorization_packet()
    replacement_authorization["authorization_id"] = "pilot-auth-replacement"
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=inspected_authorization
    )
    original_read_json_object_file = cli._read_json_object_file
    authorization_reads = 0

    def fake_read_json_object_file(path: Path):
        nonlocal authorization_reads
        if path == authorization_path:
            authorization_reads += 1
            if authorization_reads == 1:
                return inspected_authorization
            return replacement_authorization
        return original_read_json_object_file(path)

    monkeypatch.setattr(cli, "_read_json_object_file", fake_read_json_object_file)

    exit_code, report, _json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 0
    assert authorization_reads == 1
    assert report["authorization_id"] == "pilot-auth-issue-292"
    assert report["authorization_fingerprint"] == _expected_fingerprint(
        inspected_authorization
    )
    assert report["authorization_fingerprint"] != _expected_fingerprint(
        replacement_authorization
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda package: package.pop("authorization_id"),
        lambda package: package.__setitem__("extra", "safe-extra"),
        lambda package: package.__setitem__(
            "objective", "Document unsafe café unicode."
        ),
    ],
)
def test_codex_pilot_fingerprint_payload_uncertainty_fails_closed(mutation):
    package = _valid_authorization_packet()
    mutation(package)

    with pytest.raises(ValueError):
        cli._codex_pilot_authorization_fingerprint(package)


@pytest.mark.parametrize(
    ("runtime_kwargs", "expected"),
    [
        ({"executable_found": False}, "composite preflight blocked"),
        ({"timeout_argv": ["codex", "--version"]}, "composite preflight blocked"),
        ({"help_stdout": ""}, "composite preflight blocked"),
    ],
)
def test_codex_pilot_fingerprint_authorization_failure_is_sanitized(
    tmp_path, capsys, monkeypatch, runtime_kwargs, expected
):
    _install_runtime_mocks(monkeypatch, **runtime_kwargs)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )
    text_exit, text_output = _run_text(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert text_exit == 1
    assert report["authorization_inspection_passed"] is False
    assert report["authorization_fingerprint_valid"] is False
    assert report["authorization_fingerprint"] is None
    assert expected in report["blockers_by_source"]["authorization"]
    _assert_false_flags(report)
    _assert_no_leakage(json_output)
    _assert_no_leakage(text_output)


@pytest.mark.parametrize(
    "authorization_update",
    [
        {"handoff_id": "other-handoff"},
        {"repository": "Phoenix-AI-Platform/other"},
        {"branch_name": "codex/.hidden"},
    ],
)
def test_codex_pilot_fingerprint_invalid_authorization_blocks_without_payload(
    tmp_path, capsys, monkeypatch, authorization_update
):
    _install_runtime_mocks(monkeypatch)
    authorization = _valid_authorization_packet()
    authorization.update(authorization_update)
    handoff_path, evidence_path, authorization_path = _write_all(
        tmp_path, authorization=authorization
    )

    exit_code, report, json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 1
    assert report["authorization_inspection_passed"] is False
    assert report["authorization_fingerprint_valid"] is False
    assert report["authorization_fingerprint"] is None
    assert "canonical" not in json_output.lower()
    _assert_no_leakage(json_output)


def test_codex_pilot_fingerprint_no_subprocess_beyond_runtime_probe(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path, authorization_path = _write_all(tmp_path)

    exit_code, _report, _json_output = _run_json(
        handoff_path, evidence_path, authorization_path, capsys
    )

    assert exit_code == 0
    assert calls == [["codex", "--version"], ["codex", "exec", "--help"]]
