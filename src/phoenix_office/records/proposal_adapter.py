"""Adapters from stored records to proposal input models."""

from datetime import date

from phoenix_office.models.proposal import (
    CompanyConfig,
    PricingLine,
    ProposalInput,
    ScopeItem,
)
from phoenix_office.models.records import CustomerRecord, JobRecord


def create_proposal_input_from_records(
    *,
    customer: CustomerRecord,
    job: JobRecord,
    proposal_date: date,
    item_description: str,
    scope_items: list[ScopeItem],
    pricing: PricingLine,
    notes: list[str] | None = None,
    company_config: CompanyConfig | None = None,
) -> ProposalInput:
    """Create explicit proposal input from matching customer and job records.

    This adapter is a narrow bridge from stored records toward proposal generation. It
    does not infer scope, pricing, item descriptions, or execute proposal generation.
    """
    if customer.customer_id != job.customer_id:
        raise ValueError(
            "CustomerRecord customer_id must match JobRecord customer_id: "
            f"{customer.customer_id} != {job.customer_id}"
        )

    return ProposalInput(
        customer_name=customer.display_name,
        street_address=job.site_street_address,
        city_state_zip=job.site_city_state_zip,
        proposal_date=proposal_date,
        item_description=item_description,
        scope_items=scope_items,
        pricing=pricing,
        notes=notes or [],
        company_config=company_config or CompanyConfig(),
    )
