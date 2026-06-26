"""Tests for grouped record store factories."""

from pathlib import Path

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    InMemoryCustomerRepository,
    InMemoryJobRepository,
    RecordStore,
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    create_in_memory_record_store,
    create_sqlite_record_store,
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


def test_create_in_memory_record_store_returns_usable_repositories() -> None:
    store = create_in_memory_record_store()

    assert isinstance(store, RecordStore)
    assert isinstance(store.customers, InMemoryCustomerRepository)
    assert isinstance(store.jobs, InMemoryJobRepository)


def test_in_memory_record_store_saves_customer() -> None:
    store = create_in_memory_record_store()
    customer = _customer("cust-1", "Abby Hill")

    store.customers.save_customer(customer)

    assert store.customers.get_customer("cust-1") == customer


def test_in_memory_record_store_saves_job() -> None:
    store = create_in_memory_record_store()
    job = _job("job-1", "cust-1", "Tank Removal")

    store.jobs.save_job(job)

    assert store.jobs.get_job("job-1") == job


def test_create_sqlite_record_store_returns_usable_repositories(tmp_path: Path) -> None:
    store = create_sqlite_record_store(tmp_path / "records.sqlite")

    assert isinstance(store, RecordStore)
    assert isinstance(store.customers, SQLiteCustomerRepository)
    assert isinstance(store.jobs, SQLiteJobRepository)


def test_sqlite_record_store_persists_records_across_factory_calls(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    first_store = create_sqlite_record_store(db_path)
    customer = _customer("cust-1", "Abby Hill")
    job = _job("job-1", "cust-1", "Tank Removal")

    first_store.customers.save_customer(customer)
    first_store.jobs.save_job(job)
    second_store = create_sqlite_record_store(db_path)

    assert second_store.customers.get_customer("cust-1") == customer
    assert second_store.jobs.get_job("job-1") == job


def test_sqlite_record_store_uses_shared_database_path(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)

    assert isinstance(store.customers, SQLiteCustomerRepository)
    assert isinstance(store.jobs, SQLiteJobRepository)
    assert store.customers.db_path == db_path
    assert store.jobs.db_path == db_path


def test_record_store_exports_are_available_from_records_package(tmp_path: Path) -> None:
    memory_store = create_in_memory_record_store()
    sqlite_store = create_sqlite_record_store(tmp_path / "records.sqlite")

    assert isinstance(memory_store, RecordStore)
    assert isinstance(sqlite_store, RecordStore)
