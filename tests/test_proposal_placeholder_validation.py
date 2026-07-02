"""Tests for ProposalInput placeholder validation helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from phoenix_office.models.proposal import (
    CompanyConfig,
    PricingLine,
    ProposalInput,
    ScopeItem,
)
from phoenix_office.proposal_placeholder_validation import (
    proposal_input_placeholder_paths,
)


def _proposal_input(**overrides: object) -> ProposalInput:
    payload = {
        "customer_name": "Abby Hill",
        "street_address": "W3064 Piper Rd.",
        "city_state_zip": "Whitewater, WI 53190",
        "proposal_date": date(2026, 7, 1),
        "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
        "scope_items": [
            ScopeItem(number=1, description="Pump contents of tank"),
            ScopeItem(number=2, description="Remove tank"),
        ],
        "pricing": PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note="Price is based on normal tank removal.",
        ),
        "notes": ["Customer is responsible for access to the tank area."],
        "company_config": CompanyConfig(company_name="A-1 Tank Removal LLC"),
    }
    payload.update(overrides)
    return ProposalInput(**payload)


def test_proposal_input_placeholder_paths_returns_empty_list_for_clean_input() -> None:
    proposal = _proposal_input()

    assert proposal_input_placeholder_paths(proposal) == []


def test_proposal_input_placeholder_paths_detects_nested_placeholder_fields() -> None:
    proposal = _proposal_input(
        item_description="TODO: Replace with explicit item description.",
        scope_items=[
            ScopeItem(number=1, description="Replace with explicit scope item."),
            ScopeItem(number=2, description="Remove tank"),
        ],
        pricing=PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note="TODO: Replace with explicit pricing note.",
        ),
        notes=["TODO: Replace with explicit special note."],
        company_config=CompanyConfig(
            company_name="A-1 Tank Removal LLC",
            terms_and_conditions="Replace with explicit terms.",
        ),
    )

    assert proposal_input_placeholder_paths(proposal) == [
        "item_description",
        "scope_items[0].description",
        "pricing.pricing_note",
        "notes[0]",
        "company_config.terms_and_conditions",
    ]


def test_proposal_input_placeholder_paths_matches_markers_case_insensitively() -> None:
    proposal = _proposal_input(customer_name="todo: replace customer name")

    assert proposal_input_placeholder_paths(proposal) == ["customer_name"]


def test_proposal_input_placeholder_paths_supports_custom_markers() -> None:
    proposal = _proposal_input(notes=["PLACEHOLDER customer access note"])

    assert proposal_input_placeholder_paths(proposal, markers=("placeholder",)) == [
        "notes[0]"
    ]
