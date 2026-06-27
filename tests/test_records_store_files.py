"""Tests for RecordStore JSON file import/export helpers."""

from pathlib import Path

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    create_in_memory_record_store,
    create_sqlite_record_store,
    customer_records_from_json,
    customer_records_to_json,
    export_customer_records_file,
    export_job_records_file,
    import_customer_record_file,
    import_customer_records_file,
    import_job_record_file,
    import_job_records_file,
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


def test_import_abby_hill_customer_example_file_into_in_memory_store() -> None:
    store = create_in_memory_record_store()

    customer = import_customer_record_file(store, CUSTOMER_EXAMPLE)

    assert customer.customer_id == "customer-abby-hill"
    assert store.customers.get_customer("customer-abby-hill") == customer


def test_import_abby_hill_job_example_file_into_in_memory_store() -> None:
    store = create_in_memory_record_store()

    job = import_job_record_file(store, JOB_EXAMPLE)

    assert job.job_id == "job-abby-hill"
    assert store.jobs.get_job("job-abby-hill") == job


def test_import_customer_records_file_into_in_memory_store(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    customers = [_customer("cust-1"), _customer("cust-2")]
    path = tmp_path / "customers.json"
    path.write_text(customer_records_to_json(customers), encoding="utf-8")

    imported = import_customer_records_file(store, path)

    assert imported == customers
    assert store.customers.list_customers() == customers


def test_import_job_records_file_into_in_memory_store(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]
    path = tmp_path / "jobs.json"
    path.write_text(job_records_to_json(jobs), encoding="utf-8")

    imported = import_job_records_file(store, path)

    assert imported == jobs
    assert store.jobs.list_jobs() == jobs


def test_export_customer_records_file_from_in_memory_store(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    customers = [_customer("cust-1"), _customer("cust-2")]
    for customer in customers:
        store.customers.save_customer(customer)

    output_path = export_customer_records_file(store, tmp_path / "exports" / "customers.json")

    assert output_path == tmp_path / "exports" / "customers.json"
    assert customer_records_from_json(output_path.read_text(encoding="utf-8")) == customers


def test_export_job_records_file_from_in_memory_store(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]
    for job in jobs:
        store.jobs.save_job(job)

    output_path = export_job_records_file(store, tmp_path / "exports" / "jobs.json")

    assert output_path == tmp_path / "exports" / "jobs.json"
    assert job_records_from_json(output_path.read_text(encoding="utf-8")) == jobs


def test_export_helpers_create_parent_directories(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    customer_path = tmp_path / "nested" / "customers" / "customers.json"
    job_path = tmp_path / "nested" / "jobs" / "jobs.json"

    export_customer_records_file(store, customer_path)
    export_job_records_file(store, job_path)

    assert customer_path.exists()
    assert job_path.exists()


def test_import_abby_hill_example_files_into_sqlite_store_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    first_store = create_sqlite_record_store(db_path)

    customer = import_customer_record_file(first_store, CUSTOMER_EXAMPLE)
    job = import_job_record_file(first_store, JOB_EXAMPLE)
    second_store = create_sqlite_record_store(db_path)

    assert second_store.customers.get_customer(customer.customer_id) == customer
    assert second_store.jobs.get_job(job.job_id) == job


def test_invalid_json_file_propagates_value_error(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    path = tmp_path / "invalid.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid record JSON"):
        import_customer_record_file(store, path)


def test_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    store = create_in_memory_record_store()

    with pytest.raises(FileNotFoundError):
        import_customer_record_file(store, tmp_path / "missing.json")


def test_store_file_exports_are_available_from_records_package(tmp_path: Path) -> None:
    store = create_in_memory_record_store()
    customer_output = tmp_path / "customers.json"
    job_output = tmp_path / "jobs.json"

    assert import_customer_record_file(store, CUSTOMER_EXAMPLE)
    assert import_job_record_file(store, JOB_EXAMPLE)
    assert export_customer_records_file(store, customer_output) == customer_output
    assert export_job_records_file(store, job_output) == job_output
