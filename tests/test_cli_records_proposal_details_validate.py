"""Tests for records proposal details validation CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
DETAILS_EXAMPLE = ROOT / "examples" / "records" / "proposal_details_abby_hill.json"


def test_cli_records_proposal_details_validate_valid_fixture(capsys) -> None:
    exit_code = main(
        [
            "records",
            "proposal-details",
            "validate",
            str(DETAILS_EXAMPLE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RecordProposalDetails validation passed" in captured.out
    assert str(DETAILS_EXAMPLE) in captured.out
    assert captured.err == ""


def test_cli_records_proposal_details_validate_invalid_json(
    tmp_path: Path,
    capsys,
) -> None:
    details_path = tmp_path / "invalid_details.json"
    details_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        [
            "records",
            "proposal-details",
            "validate",
            str(details_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid RecordProposalDetails JSON:" in captured.err
    assert "Invalid record proposal details JSON" in captured.err


def test_cli_records_proposal_details_validate_invalid_data(
    tmp_path: Path,
    capsys,
) -> None:
    details_path = tmp_path / "invalid_details_data.json"
    payload = json.loads(DETAILS_EXAMPLE.read_text(encoding="utf-8"))
    payload["scope_items"] = []
    details_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(
        [
            "records",
            "proposal-details",
            "validate",
            str(details_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid RecordProposalDetails JSON:" in captured.err
    assert "Invalid record proposal details" in captured.err
