"""Tests for proposal data models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from phoenix_office.models.proposal import (
    CompanyConfig,
    PricingLine,
    ProposalInput,
    ScopeItem,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def abby_hill_scope() -> list[ScopeItem]:
    return [
        ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
        ScopeItem(number=2, description="Open and clean tank"),
        ScopeItem(number=3, description="Remove 1,000 gallon AST"),
        ScopeItem(number=4, description="Remove and dispose of tank and residual contents"),
    ]


@pytest.fixture()
def abby_hill_pricing() -> PricingLine:
    return PricingLine(
        amount=Decimal("3000.00"),
        is_starting_at=True,
        pricing_note=(
            "Price is based on normal pumping, cleaning, and removal of the tank. "
            "Additional charges may apply depending on the quantity and condition of "
            "the tank contents or if hazardous materials are encountered."
        ),
    )


@pytest.fixture()
def abby_hill_proposal(abby_hill_scope, abby_hill_pricing) -> ProposalInput:
    return ProposalInput(
        customer_name="Abby Hill",
        street_address="W3064 Piper Rd.",
        city_state_zip="Whitewater, WI",
        proposal_date=date(2024, 1, 15),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_items=abby_hill_scope,
        pricing=abby_hill_pricing,
    )


# ---------------------------------------------------------------------------
# ScopeItem
# ---------------------------------------------------------------------------


class TestScopeItem:
    def test_basic_creation(self):
        item = ScopeItem(number=1, description="Pump contents of tank")
        assert item.number == 1
        assert item.description == "Pump contents of tank"

    def test_description_with_contents_note(self):
        item = ScopeItem(number=1, description="Pump contents of tank (contents unknown)")
        assert "(contents unknown)" in item.description

    def test_number_must_be_at_least_one(self):
        with pytest.raises(ValidationError):
            ScopeItem(number=0, description="Something")

    def test_description_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            ScopeItem(number=1, description="")


# ---------------------------------------------------------------------------
# PricingLine
# ---------------------------------------------------------------------------


class TestPricingLine:
    def test_fixed_price(self):
        p = PricingLine(amount=Decimal("1500.00"))
        assert p.amount == Decimal("1500.00")
        assert p.is_starting_at is False
        assert p.pricing_note is None

    def test_starting_at_with_note(self, abby_hill_pricing):
        assert abby_hill_pricing.is_starting_at is True
        assert abby_hill_pricing.pricing_note is not None
        assert "Additional charges may apply" in abby_hill_pricing.pricing_note

    def test_amount_must_be_positive(self):
        with pytest.raises(ValidationError):
            PricingLine(amount=Decimal("0"))

    def test_amount_must_not_be_negative(self):
        with pytest.raises(ValidationError):
            PricingLine(amount=Decimal("-500.00"))

    def test_pricing_note_optional_on_fixed_price(self):
        p = PricingLine(amount=Decimal("2000.00"), is_starting_at=False, pricing_note="Note here.")
        assert p.pricing_note == "Note here."


# ---------------------------------------------------------------------------
# CompanyConfig
# ---------------------------------------------------------------------------


class TestCompanyConfig:
    def test_defaults(self):
        cfg = CompanyConfig()
        assert cfg.company_name == ""
        assert cfg.terms_and_conditions is None
        assert cfg.starting_at_label == "Starting at"
        assert cfg.total_label == "TOTAL"

    def test_custom_labels(self):
        cfg = CompanyConfig(
            company_name="ACME Contracting",
            total_label="TOTAL PRICE",
            starting_at_label="Starting from",
        )
        assert cfg.total_label == "TOTAL PRICE"
        assert cfg.starting_at_label == "Starting from"

    def test_terms_and_conditions(self):
        cfg = CompanyConfig(terms_and_conditions="All sales are final.")
        assert cfg.terms_and_conditions == "All sales are final."


# ---------------------------------------------------------------------------
# ProposalInput
# ---------------------------------------------------------------------------


class TestProposalInput:
    def test_abby_hill_proposal_is_valid(self, abby_hill_proposal):
        p = abby_hill_proposal
        assert p.customer_name == "Abby Hill"
        assert p.street_address == "W3064 Piper Rd."
        assert p.city_state_zip == "Whitewater, WI"
        assert p.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
        assert len(p.scope_items) == 4
        assert p.pricing.is_starting_at is True

    def test_scope_items_must_start_at_one(self):
        with pytest.raises(ValidationError, match="numbered sequentially"):
            ProposalInput(
                customer_name="Test",
                street_address="123 Main",
                city_state_zip="Anytown, WI 53000",
                proposal_date=date(2024, 1, 1),
                item_description="Some work",
                scope_items=[ScopeItem(number=2, description="Step 2")],
                pricing=PricingLine(amount=Decimal("1000.00")),
            )

    def test_scope_items_must_be_sequential(self):
        with pytest.raises(ValidationError, match="numbered sequentially"):
            ProposalInput(
                customer_name="Test",
                street_address="123 Main",
                city_state_zip="Anytown, WI 53000",
                proposal_date=date(2024, 1, 1),
                item_description="Some work",
                scope_items=[
                    ScopeItem(number=1, description="Step 1"),
                    ScopeItem(number=3, description="Step 3"),
                ],
                pricing=PricingLine(amount=Decimal("1000.00")),
            )

    def test_scope_items_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            ProposalInput(
                customer_name="Test",
                street_address="123 Main",
                city_state_zip="Anytown, WI 53000",
                proposal_date=date(2024, 1, 1),
                item_description="Some work",
                scope_items=[],
                pricing=PricingLine(amount=Decimal("1000.00")),
            )

    def test_customer_name_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            ProposalInput(
                customer_name="",
                street_address="123 Main",
                city_state_zip="Anytown, WI 53000",
                proposal_date=date(2024, 1, 1),
                item_description="Some work",
                scope_items=[ScopeItem(number=1, description="Step 1")],
                pricing=PricingLine(amount=Decimal("1000.00")),
            )

    def test_default_company_config(self, abby_hill_proposal):
        assert abby_hill_proposal.company_config.total_label == "TOTAL"

    def test_optional_general_notes(self, abby_hill_proposal):
        assert abby_hill_proposal.notes is None

    def test_general_notes_can_be_set(self):
        p = ProposalInput(
            customer_name="Test",
            street_address="123 Main",
            city_state_zip="Anytown, WI 53000",
            proposal_date=date(2024, 1, 1),
            item_description="Some work",
            scope_items=[ScopeItem(number=1, description="Step 1")],
            pricing=PricingLine(amount=Decimal("1000.00")),
            notes="Please call before arrival.",
        )
        assert p.notes == "Please call before arrival."
