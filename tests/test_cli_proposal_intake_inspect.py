"""Tests for A-1 proposal intake inspection CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
A1_INTAKE_JSON = ROOT / "examples" / "proposals" / "a1_residential_tank_removal_intake.json"


def test_cli_proposal_intake_inspect_example(capsys) -> None:
    exit_code = main(["proposal", "intake-inspect", str(A1_INTAKE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Customer: Jane Customer" in captured.out
    assert "Job Address: 123 Main St., Milwaukee, WI 53202" in captured.out
    assert "Proposal Date: 2026-07-01" in captured.out
    assert "Item Description: Removal of 1,000 Gallon Aboveground Storage Tank" in captured.out
    assert "Scope Count: 4" in captured.out
    assert "Pricing Amount: $3,000.00" in captured.out
    assert "Starting At: yes" in captured.out
    assert "Notes Count: 1" in captured.out
    assert captured.err == ""


def test_cli_proposal_intake_inspect_invalid_intake_fails(
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

    exit_code = main(["proposal", "intake-inspect", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: invalid A-1 proposal intake JSON:" in captured.err
    assert "pricing_lines" in captured.err
