"""Tests for supervised Codex pilot evidence package inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from phoenix_office.cli import main

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


def _valid_package() -> dict[str, Any]:
    return {
        "schema_version": "codex-pilot-evidence.v1",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "handoff_id": "pilot-evidence-issue-285",
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


def _run_json(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    exit_code = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def test_codex_pilot_evidence_valid_package_json_output(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 0
    assert report["schema_version"] == "codex-pilot-evidence.v1"
    assert report["command"] == "dev codex-pilot-evidence"
    assert report["input_filename"] == "evidence.json"
    assert report["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert report["pilot_kind"] == "docs-only-supervised"
    assert report["handoff_id"] == "pilot-evidence-issue-285"
    assert report["structural_valid"] is True
    assert report["evidence_package_complete"] is True
    assert report["required_control_count"] == 11
    assert report["verified_control_count"] == 11
    assert report["blocked_controls"] == []
    assert report["unverified_controls"] == []
    assert report["structural_blockers"] == []
    assert report["completion_blockers"] == []
    assert report["blockers"] == []
    assert report["pilot_ready"] is False
    assert report["invocation_authorized"] is False
    assert report["invocation_performed"] is False
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["mutation_performed"] is False


def test_codex_pilot_evidence_valid_package_text_output(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code = main(["dev", "codex-pilot-evidence", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Codex pilot evidence package inspection" in captured.out
    assert "Input filename: evidence.json" in captured.out
    assert "Structural valid: yes" in captured.out
    assert "Evidence package complete: yes" in captured.out
    assert "Pilot ready: no" in captured.out
    assert "Invocation authorized: no" in captured.out
    assert "Invocation performed: no" in captured.out
    assert "GitHub access performed: no" in captured.out
    assert "Network access performed: no" in captured.out
    assert "Mutation performed: no" in captured.out
    assert captured.err == ""


def test_codex_pilot_evidence_json_is_deterministic(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    first_exit = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    first = capsys.readouterr().out
    second_exit = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    second = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert first == second


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_evidence_structural_valid_but_incomplete(
    tmp_path, capsys, status
):
    package = _valid_package()
    package["controls"][0]["status"] = status
    package["controls"][0]["evidence_ref"] = ""
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is True
    assert report["evidence_package_complete"] is False
    assert report[f"{status}_controls"] == ["authentication_runner_access"]
    assert f"authentication_runner_access is {status}" in report["completion_blockers"]


@pytest.mark.parametrize(
    "field_name",
    ["control_id", "status", "evidence_ref", "reviewer_role"],
)
def test_codex_pilot_evidence_missing_control_field_fails_closed(
    tmp_path, capsys, field_name
):
    package = _valid_package()
    del package["controls"][0][field_name]
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert report["evidence_package_complete"] is False
    assert "controls[0] is missing required fields" in report["structural_blockers"]


@pytest.mark.parametrize("bad_value", [None, [], {}, 7, True, False])
@pytest.mark.parametrize(
    "field_name",
    ["control_id", "status", "evidence_ref", "reviewer_role"],
)
def test_codex_pilot_evidence_control_field_types_fail_closed(
    tmp_path, capsys, field_name, bad_value
):
    package = _valid_package()
    package["controls"][0][field_name] = bad_value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert report["evidence_package_complete"] is False
    assert any(
        f"controls[0].{field_name} must be a string" in blocker
        for blocker in report["structural_blockers"]
    )


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_evidence_missing_or_null_evidence_ref_fail_closed(
    tmp_path, capsys, status
):
    for value in ["missing", None]:
        package = _valid_package()
        package["controls"][0]["status"] = status
        if value == "missing":
            del package["controls"][0]["evidence_ref"]
        else:
            package["controls"][0]["evidence_ref"] = value
        path = _write_json(tmp_path / f"{status}.json", package)

        exit_code, report = _run_json(path, capsys)

        assert exit_code == 1
        assert report["structural_valid"] is False
        assert report["evidence_package_complete"] is False
        assert any(
            "controls[0].evidence_ref" in blocker
            for blocker in report["structural_blockers"]
        )


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_evidence_empty_evidence_ref_is_allowed_for_incomplete_controls(
    tmp_path, capsys, status
):
    package = _valid_package()
    package["controls"][0]["status"] = status
    package["controls"][0]["evidence_ref"] = ""
    path = _write_json(tmp_path / f"{status}.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is True
    assert report["evidence_package_complete"] is False
    assert report[f"{status}_controls"] == ["authentication_runner_access"]


@pytest.mark.parametrize("evidence_ref", [".", ".."])
def test_codex_pilot_evidence_rejects_dot_identifiers(tmp_path, capsys, evidence_ref):
    package = _valid_package()
    package["controls"][0]["evidence_ref"] = evidence_ref
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert report["evidence_package_complete"] is False
    assert any(
        "controls[0].evidence_ref is invalid" in blocker
        for blocker in report["structural_blockers"]
    )


def test_codex_pilot_evidence_unknown_fields_are_stable(tmp_path, capsys):
    package = _valid_package()
    package["raw_secret_field"] = "https://example.com/secret"
    package["controls"][0]["raw_control_field"] = "sk-proj-secret"
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    output = json.dumps(report, sort_keys=True)
    assert exit_code == 1
    assert "unknown package fields present" in report["structural_blockers"]
    assert "controls[0] contains unknown fields" in report["structural_blockers"]
    assert "raw_secret_field" not in output
    assert "raw_control_field" not in output
    assert "sk-proj-secret" not in output


@pytest.mark.parametrize(
    "value",
    [
        "Phoenix-AI-Platform/other",
        "https://github.com/Phoenix-AI-Platform/phoenix-office",
        "C:/Users/alice/phoenix-office",
        "sk-proj-secret",
        "token-value",
        "secret-password",
    ],
)
def test_codex_pilot_evidence_repository_and_pilot_kind_are_sanitized(
    tmp_path, capsys, value
):
    package = _valid_package()
    package["repository"] = value
    package["pilot_kind"] = value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    output = json.dumps(report, sort_keys=True)
    assert exit_code == 1
    assert report["repository"] is None
    assert report["pilot_kind"] is None
    assert value not in output
    assert "repository is invalid" in report["structural_blockers"]
    assert "pilot_kind is invalid" in report["structural_blockers"]


def test_codex_pilot_evidence_input_filename_is_sanitized(tmp_path, capsys):
    path = tmp_path / "users-secret-token-password.json"
    _write_json(path, _valid_package())

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 0
    assert report["input_filename"] is None


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/secret",
        "C:/Users/alice/file",
        "sk-proj-secret",
        "token-value",
        "******",
        "folder/evidence",
        "..",
        ".",
    ],
)
def test_codex_pilot_evidence_rejects_unsafe_evidence_refs(tmp_path, capsys, value):
    package = _valid_package()
    package["controls"][0]["evidence_ref"] = value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    output = json.dumps(report, sort_keys=True)
    assert exit_code == 1
    assert "controls[0].evidence_ref is invalid" in report["structural_blockers"]
    if value not in {".", ".."}:
        assert value not in output


def test_codex_pilot_evidence_unknown_control_id_and_status_are_stable(
    tmp_path, capsys
):
    package = _valid_package()
    package["controls"][0]["control_id"] = "C:/Users/alice/unknown-control"
    package["controls"][0]["status"] = "sk-proj-ready"
    package["controls"][0]["reviewer_role"] = "token-role"
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    output = json.dumps(report, sort_keys=True)
    assert exit_code == 1
    assert "controls[0].control_id is unknown" in report["structural_blockers"]
    assert "controls[0].status is invalid" in report["structural_blockers"]
    assert "controls[0].reviewer_role is invalid" in report["structural_blockers"]
    assert "unknown-control" not in output
    assert "sk-proj-ready" not in output
    assert "token-role" not in output


def test_codex_pilot_evidence_duplicate_controls_fail_closed(
    tmp_path, capsys
):
    package = _valid_package()
    package["controls"].append(dict(package["controls"][0]))
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert report["evidence_package_complete"] is False
    assert any(
        "controls[11].control_id is duplicated" in blocker
        for blocker in report["structural_blockers"]
    )


def test_codex_pilot_evidence_missing_controls_fail_closed(
    tmp_path, capsys
):
    package = _valid_package()
    package["controls"] = package["controls"][:-1]
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert report["evidence_package_complete"] is False
    assert "missing required controls" in report["structural_blockers"]


def test_codex_pilot_evidence_does_not_call_subprocess(tmp_path, capsys, monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("phoenix_office.cli.subprocess.run", fail)
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 0
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["mutation_performed"] is False
