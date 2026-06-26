"""Tests for customer and job record data models."""

import pytest
from pydantic import ValidationError

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType


def test_customer_record_accepts_valid_data() -> None:
    """CustomerRecord should accept a minimal set of valid data."""
    record = CustomerRecord(
        customer_id="cust_123",
        display_name="Abby Hill",
    )
    assert record.customer_id == "cust_123"
    assert record.display_name == "Abby Hill"
    assert record.phone is None
    assert record.email is None
    assert record.billing_street_address is None
    assert record.billing_city_state_zip is None
    assert record.notes == []


def test_customer_record_rejects_empty_display_name() -> None:
    """CustomerRecord should reject an empty display_name."""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        CustomerRecord(
            customer_id="cust_123",
            display_name="",
        )


def test_job_record_accepts_valid_data() -> None:
    """JobRecord should accept a minimal set of valid data."""
    record = JobRecord(
        job_id="job_123",
        customer_id="cust_123",
        job_name="Tank Removal",
        site_street_address="W3064 Piper Rd.",
        site_city_state_zip="Whitewater, WI",
    )
    assert record.job_id == "job_123"
    assert record.customer_id == "cust_123"
    assert record.job_name == "Tank Removal"
    assert record.site_street_address == "W3064 Piper Rd."
    assert record.site_city_state_zip == "Whitewater, WI"
    assert record.status == JobStatus.draft
    assert record.tank_location_type == TankLocationType.unknown
    assert record.tank_size_gallons is None
    assert record.tank_contents is None
    assert record.contents_known is False
    assert record.scope_notes == []
    assert record.internal_notes == []


def test_job_record_rejects_empty_required_strings() -> None:
    """JobRecord should reject empty required strings."""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        JobRecord(
            job_id="",
            customer_id="cust_123",
            job_name="Tank Removal",
            site_street_address="W3064 Piper Rd.",
            site_city_state_zip="Whitewater, WI",
        )


def test_job_record_rejects_nonpositive_tank_size() -> None:
    """JobRecord should reject a tank_size_gallons less than or equal to 0."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        JobRecord(
            job_id="job_123",
            customer_id="cust_123",
            job_name="Tank Removal",
            site_street_address="W3064 Piper Rd.",
            site_city_state_zip="Whitewater, WI",
            tank_size_gallons=0,
        )


def test_list_defaults_are_independent() -> None:
    """Lists instantiated from default_factory should be independent."""
    customer1 = CustomerRecord(customer_id="c1", display_name="C1")
    customer2 = CustomerRecord(customer_id="c2", display_name="C2")

    customer1.notes.append("Note 1")
    assert customer1.notes == ["Note 1"]
    assert customer2.notes == []

    job1 = JobRecord(
        job_id="j1",
        customer_id="c1",
        job_name="J1",
        site_street_address="123 Main",
        site_city_state_zip="Anywhere, USA",
    )
    job2 = JobRecord(
        job_id="j2",
        customer_id="c1",
        job_name="J2",
        site_street_address="123 Main",
        site_city_state_zip="Anywhere, USA",
    )

    job1.scope_notes.append("Scope 1")
    job1.internal_notes.append("Internal 1")

    assert job1.scope_notes == ["Scope 1"]
    assert job1.internal_notes == ["Internal 1"]
    assert job2.scope_notes == []
    assert job2.internal_notes == []


def test_model_dump_includes_expected_values() -> None:
    """model_dump and model_dump_json should serialize as expected."""
    job = JobRecord(
        job_id="job_123",
        customer_id="cust_123",
        job_name="Tank Removal",
        site_street_address="W3064 Piper Rd.",
        site_city_state_zip="Whitewater, WI",
        status=JobStatus.proposed,
        tank_location_type=TankLocationType.basement,
    )

    dumped = job.model_dump()
    assert dumped["job_id"] == "job_123"
    assert dumped["status"] == "proposed"
    assert dumped["tank_location_type"] == "basement"

    json_dumped = job.model_dump_json()
    assert '"job_id":"job_123"' in json_dumped
    assert '"status":"proposed"' in json_dumped
    assert '"tank_location_type":"basement"' in json_dumped
