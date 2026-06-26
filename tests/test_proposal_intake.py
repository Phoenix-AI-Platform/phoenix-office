"""Tests for interactive proposal intake."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from phoenix_office.generators.proposal import ProposalGenerator
from phoenix_office.proposal_intake import collect_proposal_input


def scripted_prompt(answers: list[str]):
    iterator = iter(answers)

    def prompt(_message: str) -> str:
        return next(iterator)

    return prompt


def test_scripted_intake_answers_produce_valid_proposal_input():
    proposal = collect_proposal_input(
        scripted_prompt(
            [
                "Jane Customer",
                "123 Main St.",
                "Milwaukee, WI 53202",
                "2026-06-25",
                "1,000",
                "AST",
                "known",
                "fixed",
                "$3,000.00",
                "",
                "Please call before arrival.",
            ]
        ),
        today=date(2026, 6, 26),
    )

    assert proposal.customer_name == "Jane Customer"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Milwaukee, WI 53202"
    assert proposal.proposal_date == date(2026, 6, 25)
    assert proposal.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert proposal.scope_items[0].description == (
        "Remove one 1,000 gallon AST tank located at 123 Main St., Milwaukee, WI 53202."
    )
    assert proposal.pricing.amount == Decimal("3000.00")
    assert proposal.pricing.is_starting_at is False
    assert proposal.pricing.pricing_note is None
    assert proposal.notes == ["Please call before arrival."]


def test_blank_proposal_date_defaults_to_today():
    proposal = collect_proposal_input(
        scripted_prompt(
            [
                "Jane Customer",
                "123 Main St.",
                "Milwaukee, WI 53202",
                "",
                "500",
                "UST",
                "known",
                "fixed",
                "1500",
                "",
                "",
            ]
        ),
        today=date(2026, 6, 26),
    )

    assert proposal.proposal_date == date(2026, 6, 26)


def test_unknown_contents_adds_contents_unknown_to_scope_item():
    proposal = collect_proposal_input(
        scripted_prompt(
            [
                "Jane Customer",
                "123 Main St.",
                "Milwaukee, WI 53202",
                "2026-06-25",
                "500",
                "UST",
                "unknown",
                "fixed",
                "1500",
                "",
                "",
            ]
        ),
        today=date(2026, 6, 26),
    )

    assert proposal.scope_items[0].description == (
        "Remove one 500 gallon UST tank located at 123 Main St., "
        "Milwaukee, WI 53202 (contents unknown)."
    )


def test_starting_at_pricing_stores_note_as_separate_pricing_field():
    proposal = collect_proposal_input(
        scripted_prompt(
            [
                "Jane Customer",
                "123 Main St.",
                "Milwaukee, WI 53202",
                "2026-06-25",
                "500",
                "AST",
                "known",
                "starting-at",
                "1500",
                "Additional charges may apply after inspection.",
                "",
            ]
        ),
        today=date(2026, 6, 26),
    )

    fields = ProposalGenerator().prepare(proposal)

    assert proposal.pricing.is_starting_at is True
    assert proposal.pricing.pricing_note == "Additional charges may apply after inspection."
    assert fields.total_line == "TOTAL: Starting at $1,500.00"
    assert "Additional charges" not in fields.total_line
    assert fields.pricing_note == "Additional charges may apply after inspection."
