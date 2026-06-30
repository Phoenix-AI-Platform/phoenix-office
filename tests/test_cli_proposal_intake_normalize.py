"""Tests for A-1 proposal intake normalization CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput

ROOT = Path(__file__).parents[1]
A1_INTAKE_JSON = ROOT / "examples" / "proposals" / "a1_residential_tank_removal_intake.json"


def test_cli_proposal_intake_normalize_example(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "normalized_proposal_input.json"

    exit_code = main(
        ["proposal", "intake-normalize", str(A1_INTAKE_JSON), str(output_path)]
    )

    captured = capsys.readouterr()
    output_payload = json.loads(output_path.read_text(encoding="utf-8"))
    proposal = ProposalInput.model_validate(output_payload)

    assert exit_code == 0
    assert "Normalized proposal intake JSON" in captured.out
    assert str(output_path) in captured.out
    assert captured.err == ""
    assert proposal.customer_name == "Jane Customer"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Milwaukee, WI 53202"
    assert proposal.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert proposal.pricing.amount == 3000
    assert proposal.pricing.is_starting_at is True
    assert len(proposal.scope_items) == 4
    assert proposal.scope_items[0].description == "Pump contents of tank (contents unknown)"
    assert proposal.notes == ["Customer is responsible for access to the tank area."]
    assert proposal.company_config.company_name == "A-1 Tank Removal LLC"


def test_cli_proposal_intake_normalize_invalid_intake_fails(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "invalid_a1_intake.json"
    output_path = tmp_path / "normalized_proposal_input.json"
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

    exit_code = main(
        ["proposal", "intake-normalize", str(input_path), str(output_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: invalid A-1 proposal intake JSON:" in captured.err
    assert "pricing_lines" in captured.err
    assert not output_path.exists()
