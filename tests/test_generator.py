"""Tests for the proposal generator foundation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from phoenix_office.generators.proposal import ProposalFields, ProposalGenerator
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
def generator() -> ProposalGenerator:
    return ProposalGenerator()


@pytest.fixture()
def abby_hill_proposal() -> ProposalInput:
    return ProposalInput(
        customer_name="Abby Hill",
        street_address="W3064 Piper Rd.",
        city_state_zip="Whitewater, WI",
        proposal_date=date(2024, 1, 15),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_items=[
            ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
            ScopeItem(number=2, description="Open and clean tank"),
            ScopeItem(number=3, description="Remove 1,000 gallon AST"),
            ScopeItem(number=4, description="Remove and dispose of tank and residual contents"),
        ],
        pricing=PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note=(
                "Price is based on normal pumping, cleaning, and removal of the tank. "
                "Additional charges may apply depending on the quantity and condition of "
                "the tank contents or if hazardous materials are encountered."
            ),
        ),
    )


# ---------------------------------------------------------------------------
# ProposalGenerator.render_date
# ---------------------------------------------------------------------------


class TestRenderDate:
    def test_january(self, generator):
        assert generator.render_date(date(2024, 1, 15)) == "January 15, 2024"

    def test_single_digit_day(self, generator):
        assert generator.render_date(date(2024, 3, 5)) == "March 5, 2024"

    def test_december(self, generator):
        assert generator.render_date(date(2023, 12, 31)) == "December 31, 2023"

    def test_invalid_type_raises(self, generator):
        with pytest.raises(TypeError):
            generator.render_date("2024-01-15")


# ---------------------------------------------------------------------------
# ProposalGenerator.render_amount
# ---------------------------------------------------------------------------


class TestRenderAmount:
    def test_thousands_separator(self, generator):
        assert generator.render_amount(Decimal("3000.00")) == "$3,000.00"

    def test_small_amount(self, generator):
        assert generator.render_amount(Decimal("500.00")) == "$500.00"

    def test_large_amount(self, generator):
        assert generator.render_amount(Decimal("10000.50")) == "$10,000.50"


# ---------------------------------------------------------------------------
# ProposalGenerator.render_scope_block
# ---------------------------------------------------------------------------


class TestRenderScopeBlock:
    def test_single_item(self, generator):
        items = [ScopeItem(number=1, description="Pump contents of tank (contents unknown)")]
        result = generator.render_scope_block(items)
        assert result == "1. Pump contents of tank (contents unknown)"

    def test_multiple_items(self, generator):
        items = [
            ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
            ScopeItem(number=2, description="Open and clean tank"),
            ScopeItem(number=3, description="Remove 1,000 gallon AST"),
            ScopeItem(number=4, description="Remove and dispose of tank and residual contents"),
        ]
        result = generator.render_scope_block(items)
        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0] == "1. Pump contents of tank (contents unknown)"
        assert lines[3] == "4. Remove and dispose of tank and residual contents"

    def test_contents_note_preserved(self, generator):
        items = [ScopeItem(number=1, description="Pump contents of tank (contents unknown)")]
        assert "(contents unknown)" in generator.render_scope_block(items)


# ---------------------------------------------------------------------------
# ProposalGenerator.render_total_line
# ---------------------------------------------------------------------------


class TestRenderTotalLine:
    def test_starting_at(self, generator):
        pricing = PricingLine(amount=Decimal("3000.00"), is_starting_at=True)
        result = generator.render_total_line(pricing)
        assert result == "TOTAL: Starting at $3,000.00"

    def test_fixed_price(self, generator):
        pricing = PricingLine(amount=Decimal("1500.00"), is_starting_at=False)
        result = generator.render_total_line(pricing)
        assert result == "TOTAL: $1,500.00"

    def test_custom_total_label(self, generator):
        pricing = PricingLine(amount=Decimal("2000.00"), is_starting_at=False)
        cfg = CompanyConfig(total_label="TOTAL PRICE")
        result = generator.render_total_line(pricing, cfg)
        assert result == "TOTAL PRICE: $2,000.00"

    def test_custom_starting_at_label(self, generator):
        pricing = PricingLine(amount=Decimal("2000.00"), is_starting_at=True)
        cfg = CompanyConfig(starting_at_label="From")
        result = generator.render_total_line(pricing, cfg)
        assert result == "TOTAL: From $2,000.00"


# ---------------------------------------------------------------------------
# ProposalGenerator.render_pricing_note
# ---------------------------------------------------------------------------


class TestRenderPricingNote:
    def test_returns_note_text(self, generator):
        pricing = PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note="Additional charges may apply.",
        )
        assert generator.render_pricing_note(pricing) == "Additional charges may apply."

    def test_returns_empty_string_when_no_note(self, generator):
        pricing = PricingLine(amount=Decimal("1500.00"))
        assert generator.render_pricing_note(pricing) == ""


# ---------------------------------------------------------------------------
# ProposalGenerator.prepare — full Abby Hill integration
# ---------------------------------------------------------------------------


class TestPrepareAbbyHill:
    def test_returns_proposal_fields(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert isinstance(fields, ProposalFields)

    def test_customer_fields(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert fields.customer_name == "Abby Hill"
        assert fields.street_address == "W3064 Piper Rd."
        assert fields.city_state_zip == "Whitewater, WI"

    def test_proposal_date_formatted(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert fields.proposal_date == "January 15, 2024"

    def test_item_description(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert "1,000 Gallon" in fields.item_description

    def test_scope_block_contains_all_items(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert "1. Pump contents of tank (contents unknown)" in fields.scope_block
        assert "4. Remove and dispose of tank and residual contents" in fields.scope_block

    def test_total_line_starting_at(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert fields.total_line == "TOTAL: Starting at $3,000.00"

    def test_pricing_note_present(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert "Additional charges may apply" in fields.pricing_note

    def test_pricing_note_is_below_total_not_inline(self, generator, abby_hill_proposal):
        """Pricing note must be a separate field, not embedded in total_line."""
        fields = generator.prepare(abby_hill_proposal)
        assert "Additional charges" not in fields.total_line
        assert fields.pricing_note != ""

    def test_no_general_notes(self, generator, abby_hill_proposal):
        fields = generator.prepare(abby_hill_proposal)
        assert fields.notes == ""
