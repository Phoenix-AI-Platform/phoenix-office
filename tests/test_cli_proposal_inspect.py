"""Tests for proposal input inspection CLI command."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
EXAMPLE_JSON = ROOT / "examples" / "proposals" / "abby_hill.json"


def test_cli_proposal_inspect_valid_example(capsys) -> None:
    exit_code = main(["proposal", "inspect", str(EXAMPLE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Customer: Abby Hill" in captured.out
    assert "Item Description: Removal of 1,000 Gallon Aboveground Storage Tank" in captured.out
    assert "Scope Items: 4" in captured.out
    assert "Pricing Lines: 1" in captured.out
    assert captured.err == ""


def test_cli_proposal_inspect_invalid_json(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "invalid_proposal.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid proposal input:" in captured.err
    assert "Invalid JSON" in captured.err
