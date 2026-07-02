"""Tests for proposal input validation CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
EXAMPLE_JSON = ROOT / "examples" / "proposals" / "abby_hill.json"


def test_cli_proposal_validate_valid_example(capsys) -> None:
    exit_code = main(["proposal", "validate", str(EXAMPLE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ProposalInput validation passed" in captured.out
    assert str(EXAMPLE_JSON) in captured.out
    assert captured.err == ""


def test_cli_proposal_validate_warns_about_placeholder_text(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "placeholder_proposal.json"
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    payload["item_description"] = "TODO: Replace with explicit item description."
    payload["pricing"]["pricing_note"] = "Replace with explicit pricing note."
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["proposal", "validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ProposalInput validation passed" in captured.out
    assert "Warning: unresolved placeholder text in proposal input." in captured.err
    assert "Placeholder fields: item_description, pricing.pricing_note" in captured.err

def test_cli_proposal_validate_invalid_json(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "invalid_proposal.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["proposal", "validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid proposal input:" in captured.err
    assert "Invalid JSON" in captured.err


def test_cli_proposal_validate_invalid_data(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "invalid_proposal_data.json"
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    payload["scope_items"] = []
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["proposal", "validate", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid proposal input:" in captured.err
    assert "Validation errors:" in captured.err
    assert "- scope_items:" in captured.err
