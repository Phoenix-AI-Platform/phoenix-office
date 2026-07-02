"""Tests for A-1 proposal intake validation CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
A1_INTAKE_JSON = ROOT / "examples" / "proposals" / "a1_residential_tank_removal_intake.json"


def test_cli_proposal_intake_validate_valid_example(capsys) -> None:
    exit_code = main(["proposal", "intake-validate", str(A1_INTAKE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"A-1 proposal intake validation passed: {A1_INTAKE_JSON}" in captured.out
    assert "Customer:" not in captured.out
    assert "Scope Count:" not in captured.out
    assert captured.err == ""


def _write_placeholder_intake(tmp_path: Path) -> Path:
    input_path = tmp_path / "placeholder_a1_intake.json"
    payload = json.loads(A1_INTAKE_JSON.read_text(encoding="utf-8"))
    payload["item_description"] = "TODO: Replace with explicit item description."
    payload["scope_notes"][0] = "Replace with explicit first scope note."
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return input_path


def test_cli_proposal_intake_validate_warns_about_placeholder_text(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_intake(tmp_path)

    exit_code = main(["proposal", "intake-validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"A-1 proposal intake validation passed: {input_path}" in captured.out
    assert "Warning: unresolved placeholder text in A-1 proposal intake." in captured.err
    assert "Placeholder fields: item_description, scope_notes[0]" in captured.err

def test_cli_proposal_intake_validate_invalid_intake_fails(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "invalid_a1_intake.json"
    input_path.write_text(
        json.dumps(
            {
                "customer_name": "Jane Customer",
                "job_address": {
                    "street_address": "123 Main St.",
                    "city_state_zip": "Milwaukee, WI 53202",
                },
                "proposal_date": "2026-07-01",
                "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
                "scope_notes": ["Remove tank"],
                "pricing_lines": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["proposal", "intake-validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: invalid A-1 proposal intake JSON:" in captured.err
    assert "pricing_lines" in captured.err


def test_cli_proposal_intake_validate_missing_file_fails(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "missing_a1_intake.json"

    exit_code = main(["proposal", "intake-validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert f"Error: intake JSON input file does not exist: {input_path}" in captured.err


def test_cli_proposal_intake_validate_directory_path_fails(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(["proposal", "intake-validate", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert f"Error: intake JSON input path is not a file: {tmp_path}" in captured.err


def test_cli_proposal_intake_validate_json_valid_example(capsys) -> None:
    exit_code = main(["proposal", "intake-validate", str(A1_INTAKE_JSON), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload == {
        "error": None,
        "input_path": str(A1_INTAKE_JSON),
        "placeholder_field_paths": [],
        "status": "valid",
        "valid": True,
    }
    assert captured.err == ""


def test_cli_proposal_intake_validate_json_reports_placeholder_field_paths(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_intake(tmp_path)

    exit_code = main(["proposal", "intake-validate", str(input_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload == {
        "error": None,
        "input_path": str(input_path),
        "placeholder_field_paths": ["item_description", "scope_notes[0]"],
        "status": "valid",
        "valid": True,
    }
    assert captured.err == ""

def test_cli_proposal_intake_validate_json_invalid_intake_fails(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "invalid_a1_intake.json"
    input_path.write_text(
        json.dumps(
            {
                "customer_name": "Jane Customer",
                "job_address": {
                    "street_address": "123 Main St.",
                    "city_state_zip": "Milwaukee, WI 53202",
                },
                "proposal_date": "2026-07-01",
                "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
                "scope_notes": ["Remove tank"],
                "pricing_lines": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["proposal", "intake-validate", str(input_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["input_path"] == str(input_path)
    assert payload["status"] == "invalid"
    assert payload["valid"] is False
    assert "Invalid A-1 proposal intake" in payload["error"]
    assert "pricing_lines" in payload["error"]
    assert captured.err == ""
