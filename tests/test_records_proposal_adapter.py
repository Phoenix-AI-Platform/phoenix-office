"""Tests for adapting records into proposal input models."""

from datetime import date
from decimal import Decimal

import pytest

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ScopeItem
from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    RecordProposalDetails,
    create_proposal_input_from_record_details,
    create_proposal_input_from_records,
)


def _customer(customer_id: str = "customer-abby-hill") -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name="Abby Hill",
    )


def _job(customer_id: str = "customer-abby-hill") -> JobRecord:
    return JobRecord(
        job_id="job-abby-hill",
        customer_id=customer_id,
        job_name="Abby Hill tank removal proposal",
        site_street_address="123 Main St.",
        site_city_state_zip="Menomonee Falls, WI 53051",
        internal_notes=["Do not share this note."],
    )


def _scope_items() -> list[ScopeItem]:
    return [
        ScopeItem(
            number=1,
            description="Remove one tank from the job site.",
        )
    ]


def _pricing() -> PricingLine:
    return PricingLine(amount=Decimal("1250.00"))


def _details() -> RecordProposalDetails:
    return RecordProposalDetails(
        proposal_date=date(2026, 6, 26),
        item_description="Removal of aboveground tank",
        scope_items=_scope_items(),
        pricing=PricingLine(
            amount=Decimal("1500.00"),
            is_starting_at=True,
            pricing_note="Price may change if contents are discovered.",
        ),
        notes=["Customer requested morning scheduling."],
        company_config=CompanyConfig(
            company_name="A-1 Tank Removal",
            terms_and_conditions="Standard terms apply.",
        ),
    )


def test_create_proposal_input_from_records_maps_customer_and_job_fields() -> None:
    proposal = create_proposal_input_from_records(
        customer=_customer(),
        job=_job(),
        proposal_date=date(2026, 6, 26),
        item_description="Tank removal",
        scope_items=_scope_items(),
        pricing=_pricing(),
    )

    assert proposal.customer_name == "Abby Hill"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Menomonee Falls, WI 53051"


def test_create_proposal_input_from_records_preserves_explicit_details() -> None:
    scope_items = _scope_items()
    pricing = PricingLine(
        amount=Decimal("1500.00"),
        is_starting_at=True,
        pricing_note="Price may change if contents are discovered.",
    )
    notes = ["Customer requested morning scheduling."]
    company_config = CompanyConfig(
        company_name="A-1 Tank Removal",
        terms_and_conditions="Standard terms apply.",
    )

    proposal = create_proposal_input_from_records(
        customer=_customer(),
        job=_job(),
        proposal_date=date(2026, 6, 26),
        item_description="Removal of underground tank",
        scope_items=scope_items,
        pricing=pricing,
        notes=notes,
        company_config=company_config,
    )

    assert proposal.proposal_date == date(2026, 6, 26)
    assert proposal.item_description == "Removal of underground tank"
    assert proposal.scope_items == scope_items
    assert proposal.pricing == pricing
    assert proposal.notes == notes
    assert proposal.company_config == company_config


def test_create_proposal_input_from_records_uses_default_config_without_mutation() -> None:
    customer = _customer()
    job = _job()
    original_customer = customer.model_copy(deep=True)
    original_job = job.model_copy(deep=True)

    proposal = create_proposal_input_from_records(
        customer=customer,
        job=job,
        proposal_date=date(2026, 6, 26),
        item_description="Tank removal",
        scope_items=_scope_items(),
        pricing=_pricing(),
    )

    assert proposal.company_config == CompanyConfig()
    assert customer == original_customer
    assert job == original_job


def test_create_proposal_input_from_records_rejects_mismatched_customer_ids() -> None:
    with pytest.raises(ValueError, match="customer_id must match"):
        create_proposal_input_from_records(
            customer=_customer("customer-1"),
            job=_job("customer-2"),
            proposal_date=date(2026, 6, 26),
            item_description="Tank removal",
            scope_items=_scope_items(),
            pricing=_pricing(),
        )


def test_create_proposal_input_from_records_does_not_copy_internal_notes() -> None:
    proposal = create_proposal_input_from_records(
        customer=_customer(),
        job=_job(),
        proposal_date=date(2026, 6, 26),
        item_description="Tank removal",
        scope_items=_scope_items(),
        pricing=_pricing(),
    )

    assert proposal.notes == []
    assert "Do not share this note." not in proposal.notes


def test_create_proposal_input_from_records_is_exported_from_records_package() -> None:
    assert callable(create_proposal_input_from_records)


def test_create_proposal_input_from_record_details_maps_records_and_details() -> None:
    details = _details()

    proposal = create_proposal_input_from_record_details(
        customer=_customer(),
        job=_job(),
        details=details,
    )

    assert proposal.customer_name == "Abby Hill"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Menomonee Falls, WI 53051"
    assert proposal.proposal_date == details.proposal_date
    assert proposal.item_description == details.item_description
    assert proposal.scope_items == details.scope_items
    assert proposal.pricing == details.pricing


def test_create_proposal_input_from_record_details_preserves_notes_and_config() -> None:
    details = _details()

    proposal = create_proposal_input_from_record_details(
        customer=_customer(),
        job=_job(),
        details=details,
    )

    assert proposal.notes == details.notes
    assert proposal.company_config == details.company_config


def test_create_proposal_input_from_record_details_reuses_id_validation() -> None:
    with pytest.raises(ValueError, match="customer_id must match"):
        create_proposal_input_from_record_details(
            customer=_customer("customer-1"),
            job=_job("customer-2"),
            details=_details(),
        )


def test_create_proposal_input_from_record_details_does_not_mutate_inputs() -> None:
    customer = _customer()
    job = _job()
    details = _details()
    original_customer = customer.model_copy(deep=True)
    original_job = job.model_copy(deep=True)
    original_details = details.model_copy(deep=True)

    create_proposal_input_from_record_details(
        customer=customer,
        job=job,
        details=details,
    )

    assert customer == original_customer
    assert job == original_job
    assert details == original_details


def test_create_proposal_input_from_record_details_is_exported_from_records_package() -> None:
    assert callable(create_proposal_input_from_record_details)
