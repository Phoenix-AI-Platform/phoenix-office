"""Tests for proposal starter draft JSON CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput


def test_cli_proposal_draft_json_creates_normalizable_a1_intake(
    tmp_path: Path, capsys
) -> None:
    draft_path = tmp_path / "drafts" / "a1_proposal_intake.json"
    normalized_path = tmp_path / "normalized" / "proposal_input.json"

    draft_exit_code = main(["proposal", "draft-json", str(draft_path)])

    draft_output = capsys.readouterr()
    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft_exit_code == 0
    assert "Wrote proposal draft JSON" in draft_output.out
    assert str(draft_path) in draft_output.out
    assert draft_output.err == ""
    assert draft_payload["customer_name"] == "Jane Customer"
    assert draft_payload["job_address"] == {
        "city_state_zip": "Milwaukee, WI 53202",
        "street_address": "123 Main St.",
    }
    assert draft_payload["pricing_lines"] == [
        {
            "amount": "3000.00",
            "description": "Residential tank removal",
            "is_starting_at": True,
            "pricing_note": "Price is based on normal tank removal.",
        }
    ]

    normalize_exit_code = main(
        ["proposal", "intake-normalize", str(draft_path), str(normalized_path)]
    )

    normalize_output = capsys.readouterr()
    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    proposal = ProposalInput.model_validate(normalized_payload)
    assert normalize_exit_code == 0
    assert "Normalized proposal intake JSON" in normalize_output.out
    assert normalize_output.err == ""
    assert proposal.customer_name == "Jane Customer"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Milwaukee, WI 53202"
    assert proposal.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert proposal.pricing.amount == 3000
    assert proposal.pricing.is_starting_at is True
    assert proposal.notes == ["Customer is responsible for access to the tank area."]
