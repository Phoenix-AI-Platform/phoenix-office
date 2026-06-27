"""Tests for RecordStore JSON import/export helpers."""

from pathlib import Path

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    create_in_memory_record_store,
    create_sqlite_record_store,
    customer_record_to_json,
    customer_records_from_json,
    customer_records_to_json,
    export_customer_records_json,
    export_job_records_json,
    import_customer_record_json,
    import_customer_records_json,
    import_job_record_json,
    import_job_records_json,
    job_record_to_json,
    job_records_from_json,
    job_records_to_json,
)

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"


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


def test_import_customer_record_json_into_in_memory_store() -> None:
    store = create_in_memory_record_store()
    customer = _customer("cust-1", "Abby Hill")

    imported = import_customer_record_json(store, customer_record_to_json(customer))

    assert imported == customer
    assert store.customers.get_customer("cust-1") == customer


def test_import_job_record_json_into_in_memory_store() -> None:
    store = create_in_memory_record_store()
    job = _job("job-1", "cust-1", "Tank Removal")

    imported = import_job_record_json(store, job_record_to_json(job))

    assert imported == job
    assert store.jobs.get_job("job-1") == job


def test_import_customer_records_json_into_in_memory_store() -> None:
    store = create_in_memory_record_store()
    customers = [_customer("cust-1"), _customer("cust-2")]

    imported = import_customer_records_json(store, customer_records_to_json(customers))

    assert imported == customers
    assert store.customers.list_customers() == customers


def test_import_job_records_json_into_in_memory_store() -> None:
    store = create_in_memory_record_store()
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]

    imported = import_job_records_json(store, job_records_to_json(jobs))

    assert imported == jobs
    assert store.jobs.list_jobs() == jobs


def test_export_customer_records_json_from_in_memory_store() -> None:
    store = create_in_memory_record_store()
    customers = [_customer("cust-1"), _customer("cust-2")]
    for customer in customers:
        store.customers.save_customer(customer)

    value = export_customer_records_json(store)

    assert customer_records_from_json(value) == customers


def test_export_job_records_json_from_in_memory_store() -> None:
    store = create_in_memory_record_store()
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]
    for job in jobs:
        store.jobs.save_job(job)

    value = export_job_records_json(store)

    assert job_records_from_json(value) == jobs


def test_import_abby_hill_examples_into_in_memory_store() -> None:
    store = create_in_memory_record_store()
    customer_json = CUSTOMER_EXAMPLE.read_text(encoding="utf-8")
    job_json = JOB_EXAMPLE.read_text(encoding="utf-8")

    customer = import_customer_record_json(store, customer_json)
    job = import_job_record_json(store, job_json)

    assert store.customers.get_customer("customer-abby-hill") == customer
    assert store.jobs.get_job("job-abby-hill") == job
    assert job.customer_id == customer.customer_id


def test_import_abby_hill_examples_into_sqlite_store_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    first_store = create_sqlite_record_store(db_path)
    customer_json = CUSTOMER_EXAMPLE.read_text(encoding="utf-8")
    job_json = JOB_EXAMPLE.read_text(encoding="utf-8")

    customer = import_customer_record_json(first_store, customer_json)
    job = import_job_record_json(first_store, job_json)
    second_store = create_sqlite_record_store(db_path)

    assert second_store.customers.get_customer(customer.customer_id) == customer
    assert second_store.jobs.get_job(job.job_id) == job


@pytest.mark.parametrize(
    "importer",
    [
        import_customer_record_json,
        import_job_record_json,
        import_customer_records_json,
        import_job_records_json,
    ],
)
def test_import_invalid_json_propagates_value_error(importer) -> None:
    store = create_in_memory_record_store()

    with pytest.raises(ValueError, match="Invalid record JSON"):
        importer(store, "{not valid json")


def test_store_json_exports_are_available_from_records_package() -> None:
    store = create_in_memory_record_store()

    assert import_customer_record_json(store, customer_record_to_json(_customer("cust-1")))
    assert import_job_record_json(store, job_record_to_json(_job("job-1", "cust-1")))
    assert customer_records_from_json(export_customer_records_json(store))
    assert job_records_from_json(export_job_records_json(store))
