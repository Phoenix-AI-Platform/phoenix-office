"""Tests for customer and job record JSON codec helpers."""

import json

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType
from phoenix_office.records import (
    customer_record_from_dict,
    customer_record_from_json,
    customer_record_to_dict,
    customer_record_to_json,
    customer_records_from_json,
    customer_records_to_json,
    job_record_from_dict,
    job_record_from_json,
    job_record_to_dict,
    job_record_to_json,
    job_records_from_json,
    job_records_to_json,
)


def _customer(customer_id: str, display_name: str | None = None) -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name=display_name or f"Customer {customer_id}",
    )


def _job(job_id: str, customer_id: str, job_name: str | None = None) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name=job_name or f"Job {job_id}",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
    )


def test_customer_record_dict_round_trip() -> None:
    customer = _customer("cust-1", "Abby Hill")

    data = customer_record_to_dict(customer)

    assert data["customer_id"] == "cust-1"
    assert customer_record_from_dict(data) == customer


def test_customer_record_json_round_trip() -> None:
    customer = _customer("cust-1", "Abby Hill")

    value = customer_record_to_json(customer)

    assert json.loads(value)["display_name"] == "Abby Hill"
    assert customer_record_from_json(value) == customer


def test_customer_record_list_json_round_trip() -> None:
    customers = [_customer("cust-1"), _customer("cust-2")]

    value = customer_records_to_json(customers)

    assert customer_records_from_json(value) == customers


def test_customer_optional_fields_and_notes_round_trip() -> None:
    customer = CustomerRecord(
        customer_id="cust-1",
        display_name="Abby Hill",
        phone="555-0100",
        email="abby@example.com",
        billing_street_address="123 Main St.",
        billing_city_state_zip="Milwaukee, WI 53202",
        notes=["Gate code 1234", "Prefers email"],
    )

    value = customer_record_to_json(customer)

    assert customer_record_from_json(value) == customer


def test_job_record_dict_round_trip() -> None:
    job = _job("job-1", "cust-1", "Tank Removal")

    data = job_record_to_dict(job)

    assert data["job_id"] == "job-1"
    assert job_record_from_dict(data) == job


def test_job_record_json_round_trip() -> None:
    job = _job("job-1", "cust-1", "Tank Removal")

    value = job_record_to_json(job)

    assert json.loads(value)["job_name"] == "Tank Removal"
    assert job_record_from_json(value) == job


def test_job_record_list_json_round_trip() -> None:
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]

    value = job_records_to_json(jobs)

    assert job_records_from_json(value) == jobs


def test_job_enums_serialize_as_strings_and_round_trip() -> None:
    job = JobRecord(
        job_id="job-1",
        customer_id="cust-1",
        job_name="Tank Removal",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
    )

    data = job_record_to_dict(job)

    assert data["status"] == "scheduled"
    assert data["tank_location_type"] == "underground"
    assert job_record_from_dict(data) == job


def test_job_optional_fields_and_notes_round_trip() -> None:
    job = JobRecord(
        job_id="job-1",
        customer_id="cust-1",
        job_name="Tank Removal",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
        status=JobStatus.accepted,
        tank_location_type=TankLocationType.aboveground,
        tank_size_gallons=1000,
        tank_contents="fuel oil",
        contents_known=True,
        scope_notes=["Remove tank", "Clean area"],
        internal_notes=["Call before arrival"],
    )

    value = job_record_to_json(job)

    assert job_record_from_json(value) == job


@pytest.mark.parametrize(
    "loader",
    [customer_record_from_json, job_record_from_json, customer_records_from_json, job_records_from_json],
)
def test_invalid_json_raises_value_error(loader) -> None:
    with pytest.raises(ValueError, match="Invalid record JSON"):
        loader("{not valid json")


@pytest.mark.parametrize("loader", [customer_record_from_json, job_record_from_json])
def test_non_object_json_for_single_record_raises_value_error(loader) -> None:
    with pytest.raises(ValueError, match="must be an object"):
        loader("[]")


@pytest.mark.parametrize("loader", [customer_records_from_json, job_records_from_json])
def test_non_list_json_for_list_helpers_raises_value_error(loader) -> None:
    with pytest.raises(ValueError, match="must be a list"):
        loader("{}")


def test_record_json_codec_exports_are_available_from_records_package() -> None:
    customer = _customer("cust-1")
    job = _job("job-1", "cust-1")

    assert customer_record_from_json(customer_record_to_json(customer)) == customer
    assert job_record_from_json(job_record_to_json(job)) == job
