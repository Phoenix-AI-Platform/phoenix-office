"""Tests for operator-facing ProposalInput validation errors."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
EXAMPLE_JSON = ROOT / "examples" / "proposals" / "abby_hill.json"


def test_proposal_validate_success_behavior_is_unchanged(capsys):
    exit_code = main(["proposal", "validate", str(EXAMPLE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"ProposalInput validation passed: {EXAMPLE_JSON}" in captured.out
    assert captured.err == ""


def test_proposal_validate_reports_readable_field_errors(tmp_path, capsys):
    invalid_proposal = tmp_path / "invalid-proposal.json"
    invalid_proposal.write_text(
        "{\n"
        '  "customer_name": "",\n'
        '  "street_address": "123 Main St.",\n'
        '  "city_state_zip": "Milwaukee, WI",\n'
        '  "proposal_date": "2026-06-25",\n'
        '  "item_description": "Tank removal",\n'
        '  "scope_items": [],\n'
        '  "pricing": {"amount": "0"}\n'
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(["proposal", "validate", str(invalid_proposal)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Error: invalid proposal input" in captured.err
    assert "Validation errors:" in captured.err
    assert "- customer_name:" in captured.err
    assert "- scope_items:" in captured.err
    assert "- pricing.amount:" in captured.err
    assert "pydantic_core" not in captured.err
    assert "For further information visit" not in captured.err
