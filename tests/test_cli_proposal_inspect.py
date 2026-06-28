"""Tests for proposal input inspection CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
EXAMPLE_JSON = ROOT / "examples" / "proposals" / "abby_hill.json"


def test_cli_proposal_inspect_valid_example(capsys) -> None:
    exit_code = main(["proposal", "inspect", str(EXAMPLE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Customer: Abby Hill" in captured.out
    assert "Site Address: W3064 Piper Rd., Whitewater, WI" in captured.out
    assert "Item Description: Removal of 1,000 Gallon Aboveground Storage Tank" in captured.out
    assert "Scope Items: 4" in captured.out
    assert "Pricing Lines: 1" in captured.out
    assert "Total: Starting at $3,000.00" in captured.out
    assert "Notes: none" in captured.out
    assert "Company:" not in captured.out
    assert captured.err == ""


def test_cli_proposal_inspect_includes_company_and_notes_when_present(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "proposal_with_company_and_notes.json"
    payload = {
        "customer_name": "Casey Example",
        "street_address": "123 Main St.",
        "city_state_zip": "Milwaukee, WI 53202",
        "proposal_date": "2026-06-28",
        "item_description": "Tank removal",
        "scope_items": [{"number": 1, "description": "Remove tank"}],
        "pricing": {"amount": "100.00", "is_starting_at": False},
        "notes": ["Call before arrival"],
        "company_config": {"company_name": "Acme Environmental"},
    }
    input_path.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Notes: present" in captured.out
    assert "Company: Acme Environmental" in captured.out
    assert "Total: $100.00" in captured.out
    assert captured.err == ""


def test_cli_proposal_inspect_json_output(capsys) -> None:
    exit_code = main(["proposal", "inspect", str(EXAMPLE_JSON), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["customer_name"] == "Abby Hill"
    assert payload["proposal_date"] == "2026-06-25"
    assert payload["pricing"]["amount"] == "3000.00"
    assert payload["pricing"]["is_starting_at"] is True
    assert payload["scope_items"][0]["number"] == 1
    assert captured.err == ""


def test_cli_proposal_inspect_invalid_json(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "invalid_proposal.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid proposal input:" in captured.err
    assert "Invalid JSON" in captured.err
