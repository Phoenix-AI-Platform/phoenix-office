"""Tests for supervised Codex pilot evidence package inspection."""

from __future__ import annotations

import json
from pathlib import Path

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
UNSAFE_FRAGMENTS = [
    "C:/Users/private-name",
    "/home/private-name",
    "https://example.com/secret",
    "sk-proj-super-secret",
    "token-value",
    "password=secret",
    "AppData",
]
CONTROL_FIELDS = ["control_id", "status", "evidence_ref", "reviewer_role"]
BAD_JSON_VALUES = [None, 0, True, [], {}]


def _valid_package() -> dict[str, object]:
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


def _run_json(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    exit_code = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def _run_text(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    exit_code = main(["dev", "codex-pilot-evidence", str(path)])
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, captured.out


def _assert_no_unsafe_fragments(output: str) -> None:
    for fragment in UNSAFE_FRAGMENTS:
        assert fragment not in output
    for fragment in [
        "private-name",
        "example.com",
        "sk-proj",
        "super-secret",
        "token-value",
        "password=secret",
        "AppData",
    ]:
        assert fragment not in output


def test_codex_pilot_evidence_valid_package_text_output(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code = main(["dev", "codex-pilot-evidence", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Codex pilot evidence package inspection" in captured.out
    assert "Input filename: evidence.json" in captured.out
    assert "Required controls: 11" in captured.out
    assert "Verified controls: 11" in captured.out
    assert "Evidence package complete: yes" in captured.out
    assert "Pilot ready: no" in captured.out
    assert "Invocation authorized: no" in captured.out
    assert "Invocation performed: no" in captured.out
    assert "GitHub access performed: no" in captured.out
    assert "Network access performed: no" in captured.out
    assert "Mutation performed: no" in captured.out
    assert str(tmp_path) not in captured.out
    assert captured.err == ""


def test_codex_pilot_evidence_valid_package_json_output(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code, payload = _run_json(path, capsys)

    assert exit_code == 0
    assert payload["schema_version"] == "codex-pilot-evidence.v1"
    assert payload["command"] == "dev codex-pilot-evidence"
    assert payload["input_filename"] == "evidence.json"
    assert payload["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert payload["pilot_kind"] == "docs-only-supervised"
    assert payload["handoff_id"] == "pilot-evidence-issue-285"
    assert payload["required_control_count"] == 11
    assert payload["verified_control_count"] == 11
    assert payload["structural_valid"] is True
    assert payload["evidence_package_complete"] is True
    assert payload["structural_errors"] == []
    assert payload["completion_blockers"] == []
    assert payload["pilot_ready"] is False
    assert payload["invocation_authorized"] is False
    assert payload["invocation_performed"] is False
    assert payload["github_access_performed"] is False
    assert payload["network_access_performed"] is False
    assert payload["mutation_performed"] is False
    assert payload["blockers"] == []


def test_codex_pilot_evidence_json_output_is_deterministic(tmp_path, capsys):
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    first_exit = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    first = capsys.readouterr().out
    second_exit = main(["dev", "codex-pilot-evidence", str(path), "--json"])
    second = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert first == second


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("not-json", "input file is malformed JSON"),
        ([], "input JSON root must be an object"),
    ],
)
def test_codex_pilot_evidence_bad_json_inputs_fail_closed(
    tmp_path, capsys, payload, expected
):
    path = tmp_path / "bad.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        _write_json(path, payload)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert expected in report["structural_errors"]
    assert report["evidence_package_complete"] is False


def test_codex_pilot_evidence_missing_file_fails_closed(tmp_path, capsys):
    exit_code, report = _run_json(tmp_path / "missing.json", capsys)

    assert exit_code == 1
    assert "input file is missing" in report["structural_errors"]
    assert report["input_filename"] == "missing.json"


def test_codex_pilot_evidence_unreadable_file_fails_closed(
    tmp_path, capsys, monkeypatch
):
    path = tmp_path / "unreadable.json"
    path.write_text("{}", encoding="utf-8")

    def unreadable(*_args, **_kwargs):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "open", unreadable)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert "input file is unreadable" in report["structural_errors"]
    assert "nope" not in json.dumps(report)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "wrong", "schema_version is invalid"),
        ("repository", "other/repo", "repository is invalid"),
        ("pilot_kind", "runtime", "pilot_kind is invalid"),
        ("handoff_id", "C:/Users/private-name/file", "handoff_id is invalid"),
    ],
)
def test_codex_pilot_evidence_top_level_contract_failures(
    tmp_path, capsys, field, value, expected
):
    package = _valid_package()
    package[field] = value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert expected in report["structural_errors"]
    if field == "handoff_id":
        assert report["handoff_id"] is None
        _assert_no_unsafe_fragments(json.dumps(report))
    if field == "repository":
        assert report["repository"] is None
    if field == "pilot_kind":
        assert report["pilot_kind"] is None


@pytest.mark.parametrize("field", ["pilot_ready", "invocation_authorized"])
@pytest.mark.parametrize("value", [True, 0, "false", None])
def test_codex_pilot_evidence_authorization_flags_must_be_json_false(
    tmp_path, capsys, field, value
):
    package = _valid_package()
    package[field] = value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert f"{field} must be JSON boolean false" in report["structural_errors"]
    assert report["pilot_ready"] is False
    assert report["invocation_authorized"] is False


@pytest.mark.parametrize("missing_control_id", list(CONTROL_REVIEWERS))
def test_codex_pilot_evidence_missing_control_fails_closed(
    tmp_path, capsys, missing_control_id
):
    package = _valid_package()
    package["controls"] = [
        control
        for control in package["controls"]
        if control["control_id"] != missing_control_id
    ]
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert f"missing control_id: {missing_control_id}" in report["structural_errors"]
    assert report["verified_control_count"] == 10


def test_codex_pilot_evidence_duplicate_and_unknown_controls_fail_closed(
    tmp_path, capsys
):
    package = _valid_package()
    controls = list(package["controls"])
    controls.append(dict(controls[0]))
    controls.append(
        {
            "control_id": "unknown_control",
            "status": "verified",
            "evidence_ref": "unknown-evidence",
            "reviewer_role": "human_operator",
        }
    )
    package["controls"] = controls
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert (
        "duplicate control_id: authentication_runner_access"
        in report["structural_errors"]
    )
    assert "controls[12].control_id is unknown" in report["structural_errors"]
    assert "unknown_control" not in json.dumps(report)


def test_codex_pilot_evidence_invalid_status_and_reviewer_fail_closed(
    tmp_path, capsys
):
    package = _valid_package()
    package["controls"][0]["status"] = "ready"
    package["controls"][1]["reviewer_role"] = "codex_worker"
    package["controls"][2]["reviewer_role"] = "assistant_reviewer"
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert "controls[0].status is invalid" in report["structural_errors"]
    assert "controls[1].reviewer_role is invalid" in report["structural_errors"]
    assert (
        "controls[2].reviewer_role does not match required role"
        in report["structural_errors"]
    )


def test_codex_pilot_evidence_verified_control_requires_safe_reference(
    tmp_path, capsys
):
    package = _valid_package()
    package["controls"][0]["evidence_ref"] = ""
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert (
        "controls[0].verified evidence_ref is invalid"
        in report["structural_errors"]
    )


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        "https://example.com/evidence",
        "C:/Users/private-name/file",
        "token-value",
        "sk-proj-super-secret",
        "password=secret",
        "folder/evidence",
        ".",
        "..",
    ],
)
def test_codex_pilot_evidence_rejects_unsafe_evidence_refs(
    tmp_path, capsys, unsafe_ref
):
    package = _valid_package()
    package["controls"][0]["evidence_ref"] = unsafe_ref
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    output = json.dumps(report, sort_keys=True)
    assert exit_code == 1
    _assert_no_unsafe_fragments(output)
    assert any("evidence_ref" in blocker for blocker in report["structural_errors"])


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_evidence_blocked_or_unverified_controls_return_nonzero(
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
    assert report["structural_errors"] == []
    assert (
        f"authentication_runner_access status is {status}"
        in report["completion_blockers"]
    )


def test_codex_pilot_evidence_rejects_unknown_fields(tmp_path, capsys):
    package = _valid_package()
    package["raw_evidence"] = "do not allow"
    package["controls"][0]["raw_log"] = "do not allow"
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert "unknown package fields present" in report["structural_errors"]
    assert "controls[0] contains unknown fields" in report["structural_errors"]
    assert "raw_evidence" not in json.dumps(report)
    assert "raw_log" not in json.dumps(report)


def test_codex_pilot_evidence_adversarial_values_do_not_leak_json_or_text(
    tmp_path, capsys
):
    package = _valid_package()
    package.update(
        {
            "schema_version": UNSAFE_FRAGMENTS[3],
            "repository": UNSAFE_FRAGMENTS[0],
            "pilot_kind": UNSAFE_FRAGMENTS[2],
            "handoff_id": UNSAFE_FRAGMENTS[1],
            UNSAFE_FRAGMENTS[4]: "unsafe key",
        }
    )
    package["controls"][0]["control_id"] = UNSAFE_FRAGMENTS[5]
    package["controls"][0]["status"] = UNSAFE_FRAGMENTS[6]
    package["controls"][0]["reviewer_role"] = UNSAFE_FRAGMENTS[2]
    package["controls"][0]["evidence_ref"] = UNSAFE_FRAGMENTS[3]
    package["controls"][0][UNSAFE_FRAGMENTS[0]] = "unsafe control key"
    path = _write_json(tmp_path / "evidence.json", package)

    json_exit, report = _run_json(path, capsys)
    text_exit, text_output = _run_text(path, capsys)

    json_output = json.dumps(report, sort_keys=True)
    assert json_exit == 1
    assert text_exit == 1
    _assert_no_unsafe_fragments(json_output)
    _assert_no_unsafe_fragments(text_output)
    assert report["repository"] is None
    assert report["pilot_kind"] is None
    assert report["handoff_id"] is None
    assert "schema_version is invalid" in report["structural_errors"]
    assert "repository is invalid" in report["structural_errors"]
    assert "pilot_kind is invalid" in report["structural_errors"]
    assert "handoff_id is invalid" in report["structural_errors"]
    assert "unknown package fields present" in report["structural_errors"]
    assert "controls[0] contains unknown fields" in report["structural_errors"]
    assert "controls[0].control_id is unknown" in report["structural_errors"]
    assert "controls[0].status is invalid" in report["structural_errors"]
    assert "controls[0].reviewer_role is invalid" in report["structural_errors"]
    assert "controls[0].evidence_ref is invalid" in report["structural_errors"]


@pytest.mark.parametrize("filename", ["token-value.json", "password=secret.json"])
def test_codex_pilot_evidence_unsafe_input_filename_is_suppressed(
    tmp_path, capsys, filename
):
    path = _write_json(tmp_path / filename, _valid_package())

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["input_filename"] is None
    assert "input filename is unsafe" in report["structural_errors"]
    _assert_no_unsafe_fragments(json.dumps(report, sort_keys=True))


@pytest.mark.parametrize("field", CONTROL_FIELDS)
def test_codex_pilot_evidence_missing_control_fields_fail_closed(
    tmp_path, capsys, field
):
    package = _valid_package()
    del package["controls"][0][field]
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert "controls[0] is missing required fields" in report["structural_errors"]
    assert report["structural_valid"] is False


@pytest.mark.parametrize("field", CONTROL_FIELDS)
@pytest.mark.parametrize("value", BAD_JSON_VALUES)
def test_codex_pilot_evidence_control_fields_require_strings(
    tmp_path, capsys, field, value
):
    package = _valid_package()
    package["controls"][0][field] = value
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert f"controls[0].{field} must be a string" in report["structural_errors"]
    assert report["structural_valid"] is False
    output = json.dumps(report, sort_keys=True)
    assert "Traceback" not in output
    _assert_no_unsafe_fragments(output)


@pytest.mark.parametrize("status", ["blocked", "unverified"])
@pytest.mark.parametrize("missing_or_null", ["missing", None])
def test_codex_pilot_evidence_non_verified_controls_require_string_evidence_ref(
    tmp_path, capsys, status, missing_or_null
):
    package = _valid_package()
    package["controls"][0]["status"] = status
    if missing_or_null == "missing":
        del package["controls"][0]["evidence_ref"]
    else:
        package["controls"][0]["evidence_ref"] = missing_or_null
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert "controls[0].evidence_ref must be a string" in report["structural_errors"]
    assert report["structural_valid"] is False


@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_codex_pilot_evidence_non_verified_controls_allow_empty_evidence_ref(
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
    assert report["structural_errors"] == []
    assert report[f"{status}_controls"] == ["authentication_runner_access"]


@pytest.mark.parametrize("missing_or_null", ["", None])
def test_codex_pilot_evidence_verified_control_requires_non_empty_string_ref(
    tmp_path, capsys, missing_or_null
):
    package = _valid_package()
    package["controls"][0]["evidence_ref"] = missing_or_null
    path = _write_json(tmp_path / "evidence.json", package)

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 1
    assert report["structural_valid"] is False
    assert any("evidence_ref" in error for error in report["structural_errors"])


def test_codex_pilot_evidence_does_not_call_external_tools(
    tmp_path, capsys, monkeypatch
):
    def fail(*_args, **_kwargs):
        raise AssertionError("external behavior must not run")

    monkeypatch.setattr("subprocess.run", fail)
    path = _write_json(tmp_path / "evidence.json", _valid_package())

    exit_code, report = _run_json(path, capsys)

    assert exit_code == 0
    assert report["github_access_performed"] is False
    assert report["network_access_performed"] is False
    assert report["mutation_performed"] is False
