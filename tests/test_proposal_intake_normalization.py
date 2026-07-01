"""Tests for deterministic A-1 proposal intake normalization."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from phoenix_office.models.proposal import ProposalInput
from phoenix_office.models.records import CustomerRecord
from phoenix_office.proposal_intake_normalization import (
    A1JobAddress,
    A1ProposalIntake,
    A1ProposalPricingLine,
    a1_proposal_intake_draft_from_customer_record,
    a1_proposal_intake_from_customer_record,
    a1_proposal_intake_from_dict,
    a1_proposal_intake_to_proposal_input,
)

FIXTURE_PATH = Path("examples/proposals/a1_residential_tank_removal_intake.json")


def test_a1_residential_tank_removal_intake_normalizes_to_proposal_input() -> None:
    intake = A1ProposalIntake(
        customer_name="Jane Customer",
        job_address=A1JobAddress(
            street_address="123 Main St.",
            city_state_zip="Milwaukee, WI 53202",
        ),
        proposal_date=date(2026, 7, 1),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_notes=[
            "Pump contents of tank (contents unknown)",
            "Open and clean tank",
            "Remove 1,000 gallon AST",
            "Remove and dispose of tank and residual contents",
        ],
        pricing_lines=[
            A1ProposalPricingLine(
                description="Residential tank removal",
                amount=Decimal("3000.00"),
                is_starting_at=True,
                pricing_note="Price is based on normal tank removal.",
            )
        ],
        special_notes=["Customer is responsible for access to the tank area."],
    )

    proposal = a1_proposal_intake_to_proposal_input(intake)

    assert isinstance(proposal, ProposalInput)
    assert proposal.customer_name == "Jane Customer"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Milwaukee, WI 53202"
    assert proposal.proposal_date == date(2026, 7, 1)
    assert proposal.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert [item.number for item in proposal.scope_items] == [1, 2, 3, 4]
    assert [item.description for item in proposal.scope_items] == intake.scope_notes
    assert proposal.pricing.amount == Decimal("3000.00")
    assert proposal.pricing.is_starting_at is True
    assert proposal.pricing.pricing_note == "Price is based on normal tank removal."
    assert proposal.notes == ["Customer is responsible for access to the tank area."]
    assert proposal.company_config.company_name == "A-1 Tank Removal LLC"


def test_a1_intake_fixture_loads_and_normalizes_deterministically() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    intake = a1_proposal_intake_from_dict(payload)

    proposal = intake.to_proposal_input()

    assert proposal.model_dump(mode="json") == {
        "city_state_zip": "Milwaukee, WI 53202",
        "company_config": {
            "company_name": "A-1 Tank Removal LLC",
            "starting_at_label": "Starting at",
            "terms_and_conditions": None,
            "total_label": "TOTAL",
        },
        "customer_name": "Jane Customer",
        "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
        "notes": ["Customer is responsible for access to the tank area."],
        "pricing": {
            "amount": "3000.00",
            "is_starting_at": True,
            "pricing_note": (
                "Price is based on normal pumping, cleaning, and removal of the tank. "
                "Additional charges may apply if hazardous materials are encountered."
            ),
        },
        "proposal_date": "2026-07-01",
        "scope_items": [
            {"description": "Pump contents of tank (contents unknown)", "number": 1},
            {"description": "Open and clean tank", "number": 2},
            {"description": "Remove 1,000 gallon AST", "number": 3},
            {
                "description": "Remove and dispose of tank and residual contents",
                "number": 4,
            },
        ],
        "street_address": "123 Main St.",
    }


def test_a1_intake_does_not_aggregate_multiple_pricing_lines() -> None:
    intake = A1ProposalIntake(
        customer_name="Jane Customer",
        job_address=A1JobAddress(
            street_address="123 Main St.",
            city_state_zip="Milwaukee, WI 53202",
        ),
        proposal_date=date(2026, 7, 1),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_notes=["Remove one 1,000 gallon AST."],
        pricing_lines=[
            A1ProposalPricingLine(description="Removal", amount=Decimal("3000.00")),
            A1ProposalPricingLine(description="Permit", amount=Decimal("250.00")),
        ],
    )

    with pytest.raises(ValueError, match="exactly one pricing line"):
        a1_proposal_intake_to_proposal_input(intake)


def _partial_a1_intake_payload() -> dict[str, object]:
    return {
        "proposal_date": "2026-07-01",
        "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
        "scope_notes": ["Remove one 1,000 gallon AST."],
        "pricing_lines": [
            {
                "description": "Residential tank removal",
                "amount": "3000.00",
            }
        ],
    }


def _customer_record_with_job_address() -> CustomerRecord:
    return CustomerRecord(
        customer_id="cust_123",
        display_name="Jane Customer",
        job_street_address="123 Main St.",
        job_city_state_zip="Milwaukee, WI 53202",
    )


def test_a1_intake_from_customer_record_fills_unset_customer_and_job_address() -> None:
    payload = _partial_a1_intake_payload()
    original_payload = deepcopy(payload)
    customer = _customer_record_with_job_address()

    intake = a1_proposal_intake_from_customer_record(payload, customer)

    assert intake.customer_name == "Jane Customer"
    assert intake.job_address.street_address == "123 Main St."
    assert intake.job_address.city_state_zip == "Milwaukee, WI 53202"
    assert intake.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert payload == original_payload


def test_a1_intake_from_customer_record_preserves_explicit_intake_values() -> None:
    payload = {
        **_partial_a1_intake_payload(),
        "customer_name": "Explicit Intake Customer",
        "job_address": {
            "street_address": "456 Intake Ave.",
            "city_state_zip": "Madison, WI 53703",
        },
    }
    customer = _customer_record_with_job_address()

    intake = a1_proposal_intake_from_customer_record(payload, customer)

    assert intake.customer_name == "Explicit Intake Customer"
    assert intake.job_address.street_address == "456 Intake Ave."
    assert intake.job_address.city_state_zip == "Madison, WI 53703"


def test_a1_intake_from_customer_record_fills_partial_job_address_only() -> None:
    payload = {
        **_partial_a1_intake_payload(),
        "customer_name": "Explicit Intake Customer",
        "job_address": {"street_address": "456 Intake Ave."},
    }
    customer = _customer_record_with_job_address()

    intake = a1_proposal_intake_from_customer_record(payload, customer)

    assert intake.customer_name == "Explicit Intake Customer"
    assert intake.job_address.street_address == "456 Intake Ave."
    assert intake.job_address.city_state_zip == "Milwaukee, WI 53202"


def test_a1_intake_from_customer_record_does_not_use_billing_address_for_job_address() -> None:
    payload = _partial_a1_intake_payload()
    customer = CustomerRecord(
        customer_id="cust_123",
        display_name="Jane Customer",
        billing_street_address="999 Billing Rd.",
        billing_city_state_zip="Billing, WI 53000",
    )

    with pytest.raises(ValidationError, match="job_address"):
        a1_proposal_intake_from_customer_record(payload, customer)


def test_a1_intake_draft_from_customer_record_uses_customer_name_and_job_address() -> None:
    customer = CustomerRecord(
        customer_id="cust_123",
        display_name="Jane Customer",
        phone="555-0100",
        email="jane@example.com",
        billing_street_address="999 Billing Rd.",
        billing_city_state_zip="Billing, WI 53000",
        job_street_address="123 Main St.",
        job_city_state_zip="Milwaukee, WI 53202",
        notes=["Do not include internal customer notes."],
    )
    pricing_line = A1ProposalPricingLine(
        description="Residential tank removal",
        amount=Decimal("3000.00"),
        is_starting_at=True,
        pricing_note="Explicit pricing note.",
    )

    intake = a1_proposal_intake_draft_from_customer_record(
        customer=customer,
        proposal_date=date(2026, 7, 1),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_notes=["Explicitly remove one 1,000 gallon AST."],
        pricing_lines=[pricing_line],
        special_notes=["Explicit special note."],
        company_name="A-1 Tank Removal LLC",
    )

    assert intake.customer_name == "Jane Customer"
    assert intake.job_address.street_address == "123 Main St."
    assert intake.job_address.city_state_zip == "Milwaukee, WI 53202"
    assert intake.proposal_date == date(2026, 7, 1)
    assert intake.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert intake.scope_notes == ["Explicitly remove one 1,000 gallon AST."]
    assert intake.pricing_lines == [pricing_line]
    assert intake.special_notes == ["Explicit special note."]
    assert intake.company_name == "A-1 Tank Removal LLC"


def test_a1_intake_draft_from_customer_record_requires_customer_job_address() -> None:
    customer = CustomerRecord(
        customer_id="cust_123",
        display_name="Jane Customer",
        billing_street_address="999 Billing Rd.",
        billing_city_state_zip="Billing, WI 53000",
    )

    with pytest.raises(ValueError, match="job_street_address and job_city_state_zip"):
        a1_proposal_intake_draft_from_customer_record(
            customer=customer,
            proposal_date=date(2026, 7, 1),
            item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
            scope_notes=["Explicit scope."],
            pricing_lines=[
                A1ProposalPricingLine(
                    description="Residential tank removal",
                    amount=Decimal("3000.00"),
                )
            ],
            special_notes=[],
        )


def test_a1_intake_draft_from_customer_record_validates_explicit_scope() -> None:
    customer = _customer_record_with_job_address()

    with pytest.raises(ValidationError, match="scope_notes"):
        a1_proposal_intake_draft_from_customer_record(
            customer=customer,
            proposal_date=date(2026, 7, 1),
            item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
            scope_notes=[],
            pricing_lines=[
                A1ProposalPricingLine(
                    description="Residential tank removal",
                    amount=Decimal("3000.00"),
                )
            ],
            special_notes=[],
        )
