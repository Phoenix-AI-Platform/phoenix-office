"""Tests for proposal starter draft JSON CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput
from phoenix_office.models.records import CustomerRecord
from phoenix_office.records import customer_record_to_json


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


def test_cli_proposal_draft_json_refuses_existing_file(tmp_path: Path, capsys) -> None:
    draft_path = tmp_path / "a1_proposal_intake.json"
    original_content = "do not replace me\n"
    draft_path.write_text(original_content, encoding="utf-8")

    exit_code = main(["proposal", "draft-json", str(draft_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: proposal draft JSON already exists:" in captured.err
    assert "Use --force to overwrite it." in captured.err
    assert draft_path.read_text(encoding="utf-8") == original_content


def test_cli_proposal_draft_json_force_overwrites_existing_file(
    tmp_path: Path, capsys
) -> None:
    draft_path = tmp_path / "a1_proposal_intake.json"
    draft_path.write_text("replace me\n", encoding="utf-8")

    exit_code = main(["proposal", "draft-json", str(draft_path), "--force"])

    captured = capsys.readouterr()
    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Wrote proposal draft JSON" in captured.out
    assert captured.err == ""
    assert draft_payload["customer_name"] == "Jane Customer"
    assert draft_payload["pricing_lines"][0]["amount"] == "3000.00"


def test_cli_proposal_draft_json_accepts_customer_specific_fields(
    tmp_path: Path, capsys
) -> None:
    draft_path = tmp_path / "abby_hill_intake.json"
    normalized_path = tmp_path / "abby_hill_proposal_input.json"

    exit_code = main(
        [
            "proposal",
            "draft-json",
            str(draft_path),
            "--customer-name",
            "Abby Hill",
            "--street-address",
            "W3064 Piper Rd.",
            "--city-state-zip",
            "Whitewater, WI 53190",
        ]
    )

    captured = capsys.readouterr()
    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Wrote proposal draft JSON" in captured.out
    assert captured.err == ""
    assert draft_payload["customer_name"] == "Abby Hill"
    assert draft_payload["job_address"] == {
        "city_state_zip": "Whitewater, WI 53190",
        "street_address": "W3064 Piper Rd.",
    }
    assert draft_payload["item_description"] == (
        "TODO: Replace with explicit item description."
    )
    assert draft_payload["scope_notes"] == ["TODO: Replace with explicit scope item."]
    assert draft_payload["pricing_lines"] == [
        {
            "amount": "1.00",
            "description": "TODO: Replace with explicit pricing description.",
            "is_starting_at": False,
            "pricing_note": "TODO: Replace with explicit pricing note or remove this note.",
        }
    ]

    normalize_exit_code = main(
        ["proposal", "intake-normalize", str(draft_path), str(normalized_path)]
    )

    normalize_output = capsys.readouterr()
    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    proposal = ProposalInput.model_validate(normalized_payload)
    assert normalize_exit_code == 0
    assert normalize_output.err == ""
    assert proposal.customer_name == "Abby Hill"
    assert proposal.street_address == "W3064 Piper Rd."
    assert proposal.city_state_zip == "Whitewater, WI 53190"
    assert proposal.pricing.amount == 1


def test_cli_proposal_draft_json_requires_complete_customer_specific_fields(
    tmp_path: Path, capsys
) -> None:
    draft_path = tmp_path / "incomplete_customer_intake.json"

    exit_code = main(
        [
            "proposal",
            "draft-json",
            str(draft_path),
            "--customer-name",
            "Abby Hill",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "customer-specific draft requires --customer-name" in captured.err
    assert "--street-address, and --city-state-zip together" in captured.err
    assert not draft_path.exists()


def _write_customer_record(path: Path, *, include_job_address: bool = True) -> None:
    customer_kwargs = {
        "customer_id": "cust-1",
        "display_name": "Abby Hill",
        "phone": "555-0100",
        "email": "abby@example.com",
        "billing_street_address": "999 Billing Rd.",
        "billing_city_state_zip": "Billing, WI 53000",
    }
    if include_job_address:
        customer_kwargs.update(
            {
                "job_street_address": "W3064 Piper Rd.",
                "job_city_state_zip": "Whitewater, WI 53190",
            }
        )
    customer = CustomerRecord(**customer_kwargs)
    path.write_text(customer_record_to_json(customer), encoding="utf-8")


def test_cli_proposal_customer_draft_json_creates_explicit_customer_backed_intake(
    tmp_path: Path, capsys
) -> None:
    customer_path = tmp_path / "abby_customer.json"
    draft_path = tmp_path / "abby_intake.json"
    normalized_path = tmp_path / "abby_proposal_input.json"
    _write_customer_record(customer_path)

    exit_code = main(
        [
            "proposal",
            "customer-draft-json",
            str(customer_path),
            str(draft_path),
            "--proposal-date",
            "2026-07-01",
            "--item-description",
            "Removal of 1,000 Gallon Aboveground Storage Tank",
            "--scope-note",
            "Pump contents of tank (contents unknown)",
            "--scope-note",
            "Remove and dispose of tank and residual contents",
            "--pricing-description",
            "Residential tank removal",
            "--pricing-amount",
            "3000.00",
            "--pricing-note",
            "Explicit pricing note.",
            "--starting-at",
            "--special-note",
            "Explicit special note.",
        ]
    )

    captured = capsys.readouterr()
    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Wrote customer-backed proposal draft JSON" in captured.out
    assert captured.err == ""
    assert draft_payload["customer_name"] == "Abby Hill"
    assert draft_payload["job_address"] == {
        "city_state_zip": "Whitewater, WI 53190",
        "street_address": "W3064 Piper Rd.",
    }
    assert draft_payload["proposal_date"] == "2026-07-01"
    assert draft_payload["item_description"] == (
        "Removal of 1,000 Gallon Aboveground Storage Tank"
    )
    assert draft_payload["scope_notes"] == [
        "Pump contents of tank (contents unknown)",
        "Remove and dispose of tank and residual contents",
    ]
    assert draft_payload["pricing_lines"] == [
        {
            "amount": "3000.00",
            "description": "Residential tank removal",
            "is_starting_at": True,
            "pricing_note": "Explicit pricing note.",
        }
    ]
    assert draft_payload["special_notes"] == ["Explicit special note."]

    normalize_exit_code = main(
        ["proposal", "intake-normalize", str(draft_path), str(normalized_path)]
    )

    normalize_output = capsys.readouterr()
    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    proposal = ProposalInput.model_validate(normalized_payload)
    assert normalize_exit_code == 0
    assert normalize_output.err == ""
    assert proposal.customer_name == "Abby Hill"
    assert proposal.street_address == "W3064 Piper Rd."
    assert proposal.city_state_zip == "Whitewater, WI 53190"
    assert proposal.pricing.amount == 3000
    assert proposal.pricing.is_starting_at is True


def test_cli_proposal_customer_draft_json_refuses_existing_file(
    tmp_path: Path, capsys
) -> None:
    customer_path = tmp_path / "abby_customer.json"
    draft_path = tmp_path / "abby_intake.json"
    _write_customer_record(customer_path)
    draft_path.write_text("do not replace me\n", encoding="utf-8")

    exit_code = main(
        [
            "proposal",
            "customer-draft-json",
            str(customer_path),
            str(draft_path),
            "--proposal-date",
            "2026-07-01",
            "--item-description",
            "Removal of 1,000 Gallon Aboveground Storage Tank",
            "--scope-note",
            "Explicit scope.",
            "--pricing-description",
            "Residential tank removal",
            "--pricing-amount",
            "3000.00",
            "--special-note",
            "Explicit note.",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "customer-backed proposal draft JSON already exists" in captured.err
    assert "Use --force to overwrite it." in captured.err
    assert draft_path.read_text(encoding="utf-8") == "do not replace me\n"


def test_cli_proposal_customer_draft_json_requires_customer_job_address(
    tmp_path: Path, capsys
) -> None:
    customer_path = tmp_path / "abby_customer.json"
    draft_path = tmp_path / "abby_intake.json"
    _write_customer_record(customer_path, include_job_address=False)

    exit_code = main(
        [
            "proposal",
            "customer-draft-json",
            str(customer_path),
            str(draft_path),
            "--proposal-date",
            "2026-07-01",
            "--item-description",
            "Removal of 1,000 Gallon Aboveground Storage Tank",
            "--scope-note",
            "Explicit scope.",
            "--pricing-description",
            "Residential tank removal",
            "--pricing-amount",
            "3000.00",
            "--special-note",
            "Explicit note.",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "job_street_address and job_city_state_zip are required" in captured.err
    assert not draft_path.exists()
