"""Tests for read-only supervised Codex pilot readiness preflight."""

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


def _completed(argv: list[str], stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _install_runtime_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version_stdout: str = "codex-cli 1.2.3\n",
    help_stdout: str = SUPPORTED_HELP,
    version_returncode: int = 0,
    help_returncode: int = 0,
    executable_found: bool = True,
    timeout_argv: list[str] | None = None,
) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: "C:/Users/example/bin/codex.exe"
        if name == "codex" and executable_found
        else None,
    )

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if timeout_argv is not None and list(argv) == timeout_argv:
            raise subprocess.TimeoutExpired(argv, 5)
        if list(argv) == ["codex", "--version"]:
            return _completed(list(argv), version_stdout, version_returncode)
        if list(argv) == ["codex", "exec", "--help"]:
            return _completed(list(argv), help_stdout, help_returncode)
        raise AssertionError(f"Unexpected argv: {argv!r}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


def _valid_handoff_package() -> dict[str, Any]:
    package = json.loads(HANDOFF_EXAMPLE.read_text(encoding="utf-8"))
    package["expected_pr_title"] = "docs: define supervised pilot boundary"
    package["prompt"] = (
        "Use the verified Phoenix Office checkout only. Update one process "
        "documentation file for Issue #288. Do not invoke Codex from "
        "automation, mutate GitHub, or change runtime behavior."
    )
    package["required_repo_paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    package["task"]["risk_class"] = "docs-only"
    package["task"]["objective"] = (
        "Document the supervised Codex invocation pilot boundary."
    )
    package["task"]["verification_plan"]["commands"] = REQUIRED_COMMANDS
    package["task"]["allowed_resources"]["paths"] = [
        "docs/process/issue-to-codex-trigger-evaluation.md"
    ]
    return package


def _valid_evidence_package(handoff_id: str = "codex-handoff-issue-259"):
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


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_pair(
    tmp_path: Path,
    *,
    handoff: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    handoff_path = _write_json(
        tmp_path / "handoff.json",
        handoff if handoff is not None else _valid_handoff_package(),
    )
    evidence_path = _write_json(
        tmp_path / "evidence.json",
        evidence if evidence is not None else _valid_evidence_package(),
    )
    return handoff_path, evidence_path


def _run_json(
    handoff_path: Path,
    evidence_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, Any], str]:
    exit_code = main(
        [
            "dev",
            "codex-pilot-preflight",
            str(handoff_path),
            str(evidence_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out), captured.out


def _run_text(
    handoff_path: Path,
    evidence_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    exit_code = main(
        ["dev", "codex-pilot-preflight", str(handoff_path), str(evidence_path)]
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, captured.out


def test_codex_pilot_preflight_all_checks_passing_json_and_text(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path = _write_pair(tmp_path)

    exit_code, report, json_output = _run_json(handoff_path, evidence_path, capsys)
    text_exit = main(["dev", "codex-pilot-preflight", str(handoff_path), str(evidence_path)])
    text_output = capsys.readouterr().out

    assert exit_code == 0
    assert text_exit == 0
    assert report["schema_version"] == "codex-pilot-preflight.v1"
    assert report["command"] == "dev codex-pilot-preflight"
    assert report["handoff_filename"] == "handoff.json"
    assert report["evidence_filename"] == "evidence.json"
    assert report["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert report["handoff_id"] == "codex-handoff-issue-259"
    assert report["handoff_static_preflight_passed"] is True
    assert report["runtime_local_cli_ready"] is True
    assert report["evidence_structural_valid"] is True
    assert report["evidence_complete"] is True
    assert report["binding_passed"] is True
    assert report["eligible_for_authorization_review"] is True
    assert report["pilot_ready"] is False
    assert report["invocation_authorized"] is False
    assert report["invocation_performed"] is False
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["mutation_performed"] is False
    assert report["branch_created"] is False
    assert report["pull_request_created"] is False
    assert all(not blockers for blockers in report["blockers_by_source"].values())
    assert "Eligible for authorization review: yes" in text_output
    assert "Pilot ready: no" in text_output
    assert "Rendered prompt" not in text_output
    assert _valid_handoff_package()["prompt"] not in json_output


def test_codex_pilot_preflight_json_is_deterministic(tmp_path, capsys, monkeypatch):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path = _write_pair(tmp_path)

    first_exit, _first_report, first = _run_json(handoff_path, evidence_path, capsys)
    second_exit, _second_report, second = _run_json(handoff_path, evidence_path, capsys)

    assert first_exit == 0
    assert second_exit == 0
    assert first == second


def test_codex_pilot_preflight_invalid_handoff_fails_closed(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    handoff["base_branch"] = "feature"
    handoff_path, evidence_path = _write_pair(tmp_path, handoff=handoff)

    exit_code, report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["handoff_static_preflight_passed"] is False
    assert report["eligible_for_authorization_review"] is False
    assert report["blockers_by_source"]["handoff"] == [
        "handoff package failed static preflight"
    ]
    assert "Rendered prompt" not in output
    assert "feature" not in output


def test_codex_pilot_preflight_missing_handoff_file_uses_sanitized_blocker(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path = tmp_path / "missing.json"
    evidence_path = _write_json(tmp_path / "evidence.json", _valid_evidence_package())

    exit_code, report, json_output = _run_json(handoff_path, evidence_path, capsys)
    text_exit, text_output = _run_text(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert text_exit == 1
    assert report["eligible_for_authorization_review"] is False
    assert report["blockers_by_source"]["handoff"] == ["handoff package is missing"]
    assert str(tmp_path) not in json_output
    assert str(handoff_path) not in json_output
    assert str(tmp_path) not in text_output
    assert str(handoff_path) not in text_output


def test_codex_pilot_preflight_malformed_handoff_json_uses_sanitized_blocker(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text("{not-json-secret-token-value", encoding="utf-8")
    evidence_path = _write_json(tmp_path / "evidence.json", _valid_evidence_package())

    exit_code, report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["eligible_for_authorization_review"] is False
    assert report["blockers_by_source"]["handoff"] == ["handoff package is malformed"]
    assert "not-json-secret-token-value" not in output
    assert "Traceback" not in output


@pytest.mark.parametrize(
    ("field_path", "unsafe_value"),
        [
            (("repository",), "C:/Users/private-name"),
            (("base_branch",), "/home/private-name"),
            (("invocation_authorized",), "https://example.com/secret"),
            (("required_repo_paths",), ["sk-proj-super-secret"]),
            (("task", "allowed_resources", "paths"), ["password=secret"]),
        ],
)
def test_codex_pilot_preflight_adversarial_handoff_values_are_sanitized(
    tmp_path, capsys, monkeypatch, field_path, unsafe_value
):
    _install_runtime_mocks(monkeypatch)
    handoff = _valid_handoff_package()
    target = handoff
    for segment in field_path[:-1]:
        target = target[segment]
    target[field_path[-1]] = unsafe_value
    handoff_path, evidence_path = _write_pair(tmp_path, handoff=handoff)

    exit_code, report, json_output = _run_json(handoff_path, evidence_path, capsys)
    text_exit, text_output = _run_text(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert text_exit == 1
    assert report["eligible_for_authorization_review"] is False
    assert report["handoff_static_preflight_passed"] is False
    assert report["blockers_by_source"]["handoff"] == [
        "handoff package failed static preflight"
    ]
    for output in [json_output, text_output]:
        assert "C:/Users/private-name" not in output
        assert "/home/private-name" not in output
        assert "https://example.com/secret" not in output
        assert "sk-proj-super-secret" not in output
        assert "token-value" not in output
        assert "password=secret" not in output
        assert "AppData" not in output


@pytest.mark.parametrize(
    "evidence_update",
    [
        {"schema_version": "wrong"},
        {"handoff_id": "C:/Users/private-name/file"},
    ],
)
def test_codex_pilot_preflight_unsafe_or_structurally_invalid_evidence_fails_closed(
    tmp_path, capsys, monkeypatch, evidence_update
):
    _install_runtime_mocks(monkeypatch)
    evidence = _valid_evidence_package()
    evidence.update(evidence_update)
    handoff_path, evidence_path = _write_pair(tmp_path, evidence=evidence)

    exit_code, report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["evidence_structural_valid"] is False
    assert report["evidence_complete"] is False
    assert report["eligible_for_authorization_review"] is False
    assert report["blockers_by_source"]["evidence"]
    assert "C:/Users" not in output
    assert "private-name" not in output


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_preflight_incomplete_evidence_fails_closed(
    tmp_path, capsys, monkeypatch, status
):
    _install_runtime_mocks(monkeypatch)
    evidence = _valid_evidence_package()
    evidence["controls"][0]["status"] = status
    evidence["controls"][0]["evidence_ref"] = ""
    handoff_path, evidence_path = _write_pair(tmp_path, evidence=evidence)

    exit_code, report, _output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["evidence_structural_valid"] is True
    assert report["evidence_complete"] is False
    assert report["eligible_for_authorization_review"] is False
    assert report["blockers_by_source"]["evidence"]


def test_codex_pilot_preflight_handoff_evidence_id_mismatch_fails_closed(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path = _write_pair(
        tmp_path,
        evidence=_valid_evidence_package(handoff_id="other-handoff-id"),
    )

    exit_code, report, _output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["binding_passed"] is False
    assert report["handoff_id"] is None
    assert "handoff id does not match evidence package" in (
        report["blockers_by_source"]["binding"]
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("repository", "other/repo", "evidence repository is invalid"),
        ("pilot_kind", "runtime", "evidence pilot_kind is invalid"),
    ],
)
def test_codex_pilot_preflight_repository_or_pilot_kind_mismatch_fails_closed(
    tmp_path, capsys, monkeypatch, field, value, expected
):
    _install_runtime_mocks(monkeypatch)
    evidence = _valid_evidence_package()
    evidence[field] = value
    handoff_path, evidence_path = _write_pair(tmp_path, evidence=evidence)

    exit_code, report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["binding_passed"] is False
    assert expected in report["blockers_by_source"]["binding"]
    if field == "repository":
        assert value not in output
        assert report["repository"] is None
    else:
        assert report["pilot_kind"] is None


@pytest.mark.parametrize(
    ("runtime_kwargs", "expected_source"),
    [
        ({"executable_found": False}, "codex executable not found"),
        ({"timeout_argv": ["codex", "--version"]}, "timeout"),
        ({"version_returncode": 7}, "nonzero_exit"),
        ({"version_stdout": ""}, "version output was empty or malformed"),
        ({"help_stdout": ""}, "exec-help output was empty or malformed"),
        (
            {"help_stdout": SUPPORTED_HELP.replace("  --sandbox <MODE>", "")},
            "missing capability: --sandbox option",
        ),
    ],
)
def test_codex_pilot_preflight_runtime_failures_fail_closed(
    tmp_path, capsys, monkeypatch, runtime_kwargs, expected_source
):
    _install_runtime_mocks(monkeypatch, **runtime_kwargs)
    handoff_path, evidence_path = _write_pair(tmp_path)

    exit_code, report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert report["runtime_local_cli_ready"] is False
    assert report["eligible_for_authorization_review"] is False
    assert any(expected_source in blocker for blocker in report["blockers_by_source"]["runtime"])
    assert "codex-cli 1.2.3" not in output


def test_codex_pilot_preflight_unsafe_handoff_filename_blocks_eligibility(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path = _write_json(tmp_path / "token-value.json", _valid_handoff_package())
    evidence_path = _write_json(tmp_path / "evidence.json", _valid_evidence_package())

    exit_code, report, json_output = _run_json(handoff_path, evidence_path, capsys)
    text_exit, text_output = _run_text(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert text_exit == 1
    assert report["handoff_filename"] is None
    assert report["evidence_filename"] == "evidence.json"
    assert report["eligible_for_authorization_review"] is False
    assert "handoff input filename is unsafe" in report["blockers_by_source"]["handoff"]
    assert "token-value" not in json_output
    assert "token-value" not in text_output


def test_codex_pilot_preflight_unsafe_evidence_filename_blocks_eligibility(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path = _write_json(tmp_path / "handoff.json", _valid_handoff_package())
    evidence_path = _write_json(tmp_path / "password=secret.json", _valid_evidence_package())

    exit_code, report, json_output = _run_json(handoff_path, evidence_path, capsys)
    text_exit, text_output = _run_text(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert text_exit == 1
    assert report["handoff_filename"] == "handoff.json"
    assert report["evidence_filename"] is None
    assert report["eligible_for_authorization_review"] is False
    assert "evidence input filename is unsafe" in report["blockers_by_source"]["evidence"]
    assert "password=secret" not in json_output
    assert "password=secret" not in text_output


def test_codex_pilot_preflight_safe_filenames_have_no_filename_blockers(
    tmp_path, capsys, monkeypatch
):
    _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path = _write_pair(tmp_path)

    exit_code, report, _output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 0
    assert "handoff input filename is unsafe" not in report["blockers_by_source"]["handoff"]
    assert "evidence input filename is unsafe" not in report["blockers_by_source"]["evidence"]


def test_codex_pilot_preflight_no_prompt_evidence_or_runtime_leakage(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(
        monkeypatch,
        version_stdout="C:/Users/private-name/codex\ncodex-cli 1.2.3\n",
    )
    handoff = _valid_handoff_package()
    handoff["prompt"] = "SECRET PROMPT TEXT"
    evidence = _valid_evidence_package()
    evidence["controls"][0]["evidence_ref"] = "secret-evidence-ref"
    handoff_path, evidence_path = _write_pair(tmp_path, handoff=handoff, evidence=evidence)

    exit_code, _report, output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 1
    assert "SECRET PROMPT TEXT" not in output
    assert "secret-evidence-ref" not in output
    assert "C:/Users" not in output
    assert "private-name" not in output
    assert calls == [["codex", "--version"], ["codex", "exec", "--help"]]


def test_codex_pilot_preflight_does_not_call_external_tools_beyond_runtime_probe(
    tmp_path, capsys, monkeypatch
):
    calls = _install_runtime_mocks(monkeypatch)
    handoff_path, evidence_path = _write_pair(tmp_path)

    exit_code, report, _output = _run_json(handoff_path, evidence_path, capsys)

    assert exit_code == 0
    assert calls == [["codex", "--version"], ["codex", "exec", "--help"]]
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["invocation_performed"] is False
    assert report["mutation_performed"] is False
    assert report["branch_created"] is False
    assert report["pull_request_created"] is False
