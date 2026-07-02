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


def test_cli_proposal_inspect_json_includes_company_and_notes_when_present(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "proposal_with_optional_fields.json"
    payload = {
        "customer_name": "Casey Example",
        "street_address": "123 Main St.",
        "city_state_zip": "Milwaukee, WI 53202",
        "proposal_date": "2026-06-28",
        "item_description": "Tank removal",
        "scope_items": [{"number": 1, "description": "Remove tank"}],
        "pricing": {"amount": "100.00", "is_starting_at": False},
        "notes": ["Call before arrival", "Use north driveway"],
        "company_config": {
            "company_name": "Acme Environmental",
            "terms_and_conditions": "Operator-reviewed terms.",
        },
    }
    input_path.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path), "--json"])

    captured = capsys.readouterr()
    output_payload = json.loads(captured.out)
    assert exit_code == 0
    assert output_payload["customer_name"] == "Casey Example"
    assert output_payload["notes"] == ["Call before arrival", "Use north driveway"]
    assert output_payload["company_config"] == {
        "company_name": "Acme Environmental",
        "starting_at_label": "Starting at",
        "terms_and_conditions": "Operator-reviewed terms.",
        "total_label": "TOTAL",
    }
    assert captured.err == ""


def test_cli_proposal_inspect_json_defaults_omitted_notes_to_empty_list(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "proposal_without_notes.json"
    payload = {
        "customer_name": "Jordan Example",
        "street_address": "456 Oak Ave.",
        "city_state_zip": "Madison, WI 53703",
        "proposal_date": "2026-06-28",
        "item_description": "Soil sampling",
        "scope_items": [{"number": 1, "description": "Collect sample"}],
        "pricing": {"amount": "250.00", "is_starting_at": True},
    }
    input_path.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path), "--json"])

    captured = capsys.readouterr()
    output_payload = json.loads(captured.out)
    assert exit_code == 0
    assert output_payload["customer_name"] == "Jordan Example"
    assert output_payload["notes"] == []
    assert output_payload["pricing"]["amount"] == "250.00"
    assert output_payload["pricing"]["is_starting_at"] is True
    assert captured.err == ""


def _write_placeholder_proposal_input(tmp_path: Path) -> Path:
    input_path = tmp_path / "placeholder_proposal.json"
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    payload["item_description"] = "TODO: Replace with explicit item description."
    payload["pricing"]["pricing_note"] = "Replace with explicit pricing note."
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return input_path


def test_cli_proposal_inspect_warns_about_placeholder_text(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_proposal_input(tmp_path)

    exit_code = main(["proposal", "inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Customer: Abby Hill" in captured.out
    assert "Warning: unresolved placeholder text in proposal input." in captured.err
    assert "Placeholder fields: item_description, pricing.pricing_note" in captured.err


def test_cli_proposal_inspect_json_includes_placeholder_field_paths(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_proposal_input(tmp_path)

    exit_code = main(["proposal", "inspect", str(input_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["placeholder_field_paths"] == [
        "item_description",
        "pricing.pricing_note",
    ]
    assert captured.err == ""

def test_cli_proposal_inspect_invalid_json(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "invalid_proposal.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["proposal", "inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: invalid proposal input:" in captured.err
    assert "Invalid JSON" in captured.err
