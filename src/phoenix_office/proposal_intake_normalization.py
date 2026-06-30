"""Deterministic A-1 proposal intake normalization helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ProposalInput, ScopeItem

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

DEFAULT_A1_COMPANY_NAME = "A-1 Tank Removal LLC"


class A1JobAddress(BaseModel):
    """Normalized job-site address fields for an A-1 proposal intake."""

    street_address: NonEmptyText = Field(..., description="Street address of the job site.")
    city_state_zip: NonEmptyText = Field(..., description="City, state, and ZIP of the job site.")


class A1ProposalPricingLine(BaseModel):
    """Explicit intake pricing line for an A-1 proposal draft."""

    description: NonEmptyText = Field(..., description="Human-readable pricing line label.")
    amount: Decimal = Field(..., gt=0, description="Explicit price for this line in USD.")
    is_starting_at: bool = Field(
        default=False,
        description="Whether this explicit price should render as a starting-at amount.",
    )
    pricing_note: NonEmptyText | None = Field(
        default=None,
        description="Optional explicit note associated with the proposal pricing.",
    )


class A1ProposalIntake(BaseModel):
    """Rough but explicit A-1 proposal details ready for deterministic normalization."""

    customer_name: NonEmptyText = Field(..., description="Customer name for the proposal.")
    job_address: A1JobAddress = Field(..., description="Job-site address for the proposal.")
    proposal_date: date = Field(..., description="Date printed on the proposal.")
    item_description: NonEmptyText = Field(
        ...,
        description="Explicit description of the primary proposal item.",
    )
    scope_notes: list[NonEmptyText] = Field(
        ...,
        min_length=1,
        description="Explicit scope notes to convert into numbered proposal scope items.",
    )
    pricing_lines: list[A1ProposalPricingLine] = Field(
        ...,
        min_length=1,
        description="Explicit pricing lines captured during intake.",
    )
    special_notes: list[NonEmptyText] = Field(
        default_factory=list,
        description="Explicit proposal notes separate from pricing notes.",
    )
    company_name: NonEmptyText = Field(
        default=DEFAULT_A1_COMPANY_NAME,
        description="Company name used in ProposalInput company configuration.",
    )

    def to_proposal_input(self) -> ProposalInput:
        """Convert explicit intake details into the existing ProposalInput model."""
        return a1_proposal_intake_to_proposal_input(self)


def a1_proposal_intake_from_dict(value: dict[str, Any]) -> A1ProposalIntake:
    """Parse A-1 proposal intake details from a dictionary."""
    return A1ProposalIntake.model_validate(value)


def a1_proposal_intake_to_proposal_input(intake: A1ProposalIntake) -> ProposalInput:
    """Convert explicit A-1 intake details into a normalized ProposalInput draft.

    This helper does not infer missing scope or pricing. Because ProposalInput currently
    supports one pricing total, intake must provide exactly one pricing line.
    """
    pricing = _proposal_pricing_from_intake(intake.pricing_lines)
    return ProposalInput(
        customer_name=intake.customer_name,
        street_address=intake.job_address.street_address,
        city_state_zip=intake.job_address.city_state_zip,
        proposal_date=intake.proposal_date,
        item_description=intake.item_description,
        scope_items=[
            ScopeItem(number=index, description=description)
            for index, description in enumerate(intake.scope_notes, start=1)
        ],
        pricing=pricing,
        notes=list(intake.special_notes),
        company_config=CompanyConfig(company_name=intake.company_name),
    )


def _proposal_pricing_from_intake(pricing_lines: list[A1ProposalPricingLine]) -> PricingLine:
    if len(pricing_lines) != 1:
        raise ValueError(
            "A-1 proposal intake requires exactly one pricing line because "
            "ProposalInput currently stores one pricing total."
        )

    pricing_line = pricing_lines[0]
    return PricingLine(
        amount=pricing_line.amount,
        is_starting_at=pricing_line.is_starting_at,
        pricing_note=pricing_line.pricing_note,
    )
