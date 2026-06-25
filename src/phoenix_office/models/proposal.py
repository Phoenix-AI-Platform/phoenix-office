"""Proposal data models.

These Pydantic models represent the structured input required to generate a
contractor proposal.  They are intentionally company-agnostic; company-specific
formatting preferences live in :class:`CompanyConfig`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class ScopeItem(BaseModel):
    """A single numbered line item in the proposal scope of work."""

    number: Annotated[int, Field(ge=1, description="Display number for this scope item.")]
    description: str = Field(
        ...,
        min_length=1,
        description=(
            "Full text of the scope item, including any parenthetical notes "
            "such as '(contents unknown)'."
        ),
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.number}. {self.description}"


class PricingLine(BaseModel):
    """Pricing information for the proposal total."""

    amount: Decimal = Field(..., description="Total price in USD.")
    is_starting_at: bool = Field(
        default=False,
        description=(
            "When True the total renders as 'Starting at $X' and any "
            "pricing_note is placed below the total with the terms."
        ),
    )
    pricing_note: str | None = Field(
        default=None,
        description=(
            "Optional explanatory note shown below the total line, e.g. "
            "'Price is based on normal pumping, cleaning, and removal…'"
        ),
    )

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Pricing amount must be greater than zero.")
        return v


class CompanyConfig(BaseModel):
    """Company-specific formatting preferences.

    Keeping these separate from :class:`ProposalInput` ensures that
    contractor-specific conventions never bleed into the shared data model.
    """

    company_name: str = Field(default="", description="Legal name of the contracting company.")
    terms_and_conditions: str | None = Field(
        default=None,
        description="Full terms / disclaimer text printed at the bottom of the proposal.",
    )
    starting_at_label: str = Field(
        default="Starting at",
        description="Label prefix used when is_starting_at is True, e.g. 'Starting at'.",
    )
    total_label: str = Field(
        default="TOTAL",
        description="Label used for the total line, e.g. 'TOTAL'.",
    )


class ProposalInput(BaseModel):
    """Complete structured input for a contractor proposal.

    Example (Abby Hill)::

        proposal = ProposalInput(
            customer_name="Abby Hill",
            street_address="W3064 Piper Rd.",
            city_state_zip="Whitewater, WI",
            proposal_date=date(2024, 1, 1),
            item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
            scope_items=[
                ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
                ScopeItem(number=2, description="Open and clean tank"),
                ScopeItem(number=3, description="Remove 1,000 gallon AST"),
                ScopeItem(
                    number=4, description="Remove and dispose of tank and residual contents"
                ),
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
    """

    customer_name: str = Field(..., min_length=1, description="Full name of the customer.")
    street_address: str = Field(..., min_length=1, description="Street address of the job site.")
    city_state_zip: str = Field(
        ..., min_length=1, description="City, state, and ZIP of the job site."
    )
    proposal_date: date = Field(..., description="Date printed on the proposal.")
    item_description: str = Field(
        ..., min_length=1, description="Short description of the primary work item."
    )
    scope_items: list[ScopeItem] = Field(
        ...,
        min_length=1,
        description="Ordered list of numbered scope-of-work items.",
    )
    pricing: PricingLine = Field(..., description="Pricing total and related notes.")
    notes: list[str] = Field(
        default_factory=list,
        description="General proposal notes separate from the pricing note.",
    )
    company_config: CompanyConfig = Field(
        default_factory=CompanyConfig,
        description="Company-specific formatting preferences.",
    )

    @field_validator("scope_items")
    @classmethod
    def scope_items_must_be_sequentially_numbered(
        cls, items: list[ScopeItem]
    ) -> list[ScopeItem]:
        for idx, item in enumerate(items, start=1):
            if item.number != idx:
                raise ValueError(
                    f"Scope item at position {idx} has number {item.number}; "
                    f"expected {idx}.  Items must be numbered sequentially starting at 1."
                )
        return items
