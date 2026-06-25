"""Proposal generator foundation.

:class:`ProposalGenerator` converts a :class:`~phoenix_office.models.proposal.ProposalInput`
into a :class:`ProposalFields` mapping — a plain dictionary of rendered text strings ready
to be injected into a DOCX template or passed to a PDF renderer.

This module intentionally stops short of file I/O so that it can be tested
in isolation and so that multiple output formats (DOCX, PDF, plain-text
preview) can share the same rendering logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ProposalInput, ScopeItem


@dataclass
class ProposalFields:
    """Rendered text fields ready for template injection.

    All monetary values are pre-formatted strings (e.g. ``"$3,000.00"``).
    The ``scope_block`` field contains the full numbered scope of work as a
    single newline-delimited string.

    Attributes:
        customer_name: Full customer name.
        street_address: Job-site street address.
        city_state_zip: City, state, and ZIP string.
        proposal_date: Proposal date formatted as ``MMMM D, YYYY``.
        item_description: Short description of the primary work item.
        scope_block: Numbered scope items joined by newlines.
        total_line: Formatted total line, e.g. ``"TOTAL: Starting at $3,000.00"``.
        pricing_note: Pricing note placed below the total (may be empty string).
        notes: General proposal notes (may be empty string).
    """

    customer_name: str
    street_address: str
    city_state_zip: str
    proposal_date: str
    item_description: str
    scope_block: str
    total_line: str
    pricing_note: str = field(default="")
    notes: str = field(default="")


class ProposalGenerator:
    """Converts a :class:`ProposalInput` into rendered :class:`ProposalFields`.

    Usage::

        from phoenix_office.generators.proposal import ProposalGenerator

        fields = ProposalGenerator().prepare(proposal)
        # fields.total_line == "TOTAL: Starting at $3,000.00"
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prepare(self, proposal: ProposalInput) -> ProposalFields:
        """Render all proposal fields into a :class:`ProposalFields` instance.

        Args:
            proposal: Validated :class:`ProposalInput`.

        Returns:
            :class:`ProposalFields` with every field rendered as a string.
        """
        cfg = proposal.company_config
        return ProposalFields(
            customer_name=proposal.customer_name,
            street_address=proposal.street_address,
            city_state_zip=proposal.city_state_zip,
            proposal_date=self.render_date(proposal.proposal_date),
            item_description=proposal.item_description,
            scope_block=self.render_scope_block(proposal.scope_items),
            total_line=self.render_total_line(proposal.pricing, cfg),
            pricing_note=self.render_pricing_note(proposal.pricing),
            notes="\n".join(proposal.notes),
        )

    # ------------------------------------------------------------------
    # Rendering helpers (public so they can be called/tested individually)
    # ------------------------------------------------------------------

    def render_date(self, d: object) -> str:  # accepts ``datetime.date``
        """Format a date as ``Month D, YYYY`` (e.g. ``January 1, 2024``)."""
        from datetime import date as date_type

        if not isinstance(d, date_type):
            raise TypeError(f"Expected datetime.date, got {type(d)!r}")
        return d.strftime("%B %-d, %Y")

    def render_scope_block(self, items: list[ScopeItem]) -> str:
        """Render all scope items as a numbered list joined by newlines.

        Args:
            items: Ordered list of :class:`ScopeItem` objects.

        Returns:
            Multi-line string, e.g.::

                1. Pump contents of tank (contents unknown)
                2. Open and clean tank
        """
        return "\n".join(f"{item.number}. {item.description}" for item in items)

    def render_amount(self, amount: Decimal) -> str:
        """Format a decimal amount as a USD currency string, e.g. ``$3,000.00``."""
        return f"${amount:,.2f}"

    def render_total_line(self, pricing: PricingLine, config: CompanyConfig | None = None) -> str:
        """Render the total line according to A-1 formatting conventions.

        Args:
            pricing: The :class:`PricingLine` for this proposal.
            config: Optional :class:`CompanyConfig` controlling label text.

        Returns:
            A string such as ``"TOTAL: Starting at $3,000.00"`` or
            ``"TOTAL: $3,000.00"``.
        """
        cfg = config or CompanyConfig()
        amount_str = self.render_amount(pricing.amount)
        if pricing.is_starting_at:
            value_str = f"{cfg.starting_at_label} {amount_str}"
        else:
            value_str = amount_str
        return f"{cfg.total_label}: {value_str}"

    def render_pricing_note(self, pricing: PricingLine) -> str:
        """Return the pricing note string (empty string if none).

        Per A-1 convention the pricing note is placed *below* the TOTAL line
        alongside the terms/disclaimers — not inline with the total.  This
        method simply surfaces the note text; template renderers decide where
        to place it on the page.
        """
        return pricing.pricing_note or ""
