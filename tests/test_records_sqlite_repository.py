"""Tests for SQLite customer and job repositories."""

import sqlite3
from pathlib import Path

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType
from phoenix_office.records import (
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    initialize_records_database,
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


def test_initialize_records_database_creates_usable_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"

    initialize_records_database(db_path)

    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"customers", "jobs"}.issubset(table_names)


def test_sqlite_customer_repository_saves_and_gets_customer(tmp_path: Path) -> None:
    repository = SQLiteCustomerRepository(tmp_path / "records.sqlite")
    customer = _customer("cust-1", "Abby Hill")

    saved = repository.save_customer(customer)

    assert saved is customer
    assert repository.get_customer("cust-1") == customer


def test_sqlite_customer_repository_missing_customer_returns_none(tmp_path: Path) -> None:
    repository = SQLiteCustomerRepository(tmp_path / "records.sqlite")

    assert repository.get_customer("missing") is None


def test_sqlite_customer_repository_overwrites_same_customer_id(tmp_path: Path) -> None:
    repository = SQLiteCustomerRepository(tmp_path / "records.sqlite")
    original = _customer("cust-1", "Original")
    replacement = _customer("cust-1", "Replacement")

    repository.save_customer(original)
    repository.save_customer(replacement)

    assert repository.get_customer("cust-1") == replacement
    assert repository.list_customers() == [replacement]


def test_sqlite_customer_repository_lists_in_insertion_order(tmp_path: Path) -> None:
    repository = SQLiteCustomerRepository(tmp_path / "records.sqlite")
    first = _customer("cust-1")
    second = _customer("cust-2")
    third = _customer("cust-3")

    repository.save_customer(first)
    repository.save_customer(second)
    repository.save_customer(third)

    assert repository.list_customers() == [first, second, third]


def test_sqlite_customer_repository_preserves_customer_notes(tmp_path: Path) -> None:
    repository = SQLiteCustomerRepository(tmp_path / "records.sqlite")
    customer = CustomerRecord(
        customer_id="cust-1",
        display_name="Abby Hill",
        notes=["Gate code 1234", "Prefers email"],
    )

    repository.save_customer(customer)

    assert repository.get_customer("cust-1") == customer


def test_sqlite_customer_data_persists_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    first_repository = SQLiteCustomerRepository(db_path)
    customer = _customer("cust-1", "Abby Hill")

    first_repository.save_customer(customer)
    second_repository = SQLiteCustomerRepository(db_path)

    assert second_repository.get_customer("cust-1") == customer


def test_sqlite_job_repository_saves_and_gets_job(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    job = _job("job-1", "cust-1", "Tank Removal")

    saved = repository.save_job(job)

    assert saved is job
    assert repository.get_job("job-1") == job


def test_sqlite_job_repository_missing_job_returns_none(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")

    assert repository.get_job("missing") is None


def test_sqlite_job_repository_overwrites_same_job_id(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    original = _job("job-1", "cust-1", "Original")
    replacement = _job("job-1", "cust-1", "Replacement")

    repository.save_job(original)
    repository.save_job(replacement)

    assert repository.get_job("job-1") == replacement
    assert repository.list_jobs() == [replacement]


def test_sqlite_job_repository_lists_in_insertion_order(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    first = _job("job-1", "cust-1")
    second = _job("job-2", "cust-2")
    third = _job("job-3", "cust-1")

    repository.save_job(first)
    repository.save_job(second)
    repository.save_job(third)

    assert repository.list_jobs() == [first, second, third]


def test_sqlite_job_repository_filters_jobs_for_customer(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    first = _job("job-1", "cust-1")
    other = _job("job-2", "cust-2")
    second = _job("job-3", "cust-1")

    repository.save_job(first)
    repository.save_job(other)
    repository.save_job(second)

    assert repository.list_jobs_for_customer("cust-1") == [first, second]
    assert repository.list_jobs_for_customer("cust-2") == [other]
    assert repository.list_jobs_for_customer("missing") == []


def test_sqlite_job_repository_preserves_job_field_types(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    job = JobRecord(
        job_id="job-1",
        customer_id="cust-1",
        job_name="Tank Removal",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=1000,
        tank_contents="fuel oil",
        contents_known=True,
        scope_notes=["Remove tank", "Backfill excavation"],
        internal_notes=["Confirm utility marks"],
    )

    repository.save_job(job)
    loaded = repository.get_job("job-1")

    assert loaded == job
    assert loaded is not None
    assert loaded.status == JobStatus.scheduled
    assert loaded.tank_location_type == TankLocationType.underground
    assert loaded.tank_size_gallons == 1000
    assert loaded.contents_known is True
    assert loaded.scope_notes == ["Remove tank", "Backfill excavation"]
    assert loaded.internal_notes == ["Confirm utility marks"]


def test_sqlite_job_repository_preserves_optional_tank_size(tmp_path: Path) -> None:
    repository = SQLiteJobRepository(tmp_path / "records.sqlite")
    job = _job("job-1", "cust-1")

    repository.save_job(job)

    loaded = repository.get_job("job-1")
    assert loaded is not None
    assert loaded.tank_size_gallons is None


def test_sqlite_job_data_persists_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    first_repository = SQLiteJobRepository(db_path)
    job = _job("job-1", "cust-1", "Tank Removal")

    first_repository.save_job(job)
    second_repository = SQLiteJobRepository(db_path)

    assert second_repository.get_job("job-1") == job
