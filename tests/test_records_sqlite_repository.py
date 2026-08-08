"""Tests for SQLite customer and job repositories."""

import hashlib
import sqlite3
from pathlib import Path

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType
from phoenix_office.records import (
    CustomerAlreadyExistsError,
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    initialize_records_database,
)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_signature(db_path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()


def _sqlite_sidecars(db_path: Path) -> list[Path]:
    return [
        Path(f"{db_path}{suffix}")
        for suffix in ("-wal", "-shm", "-journal")
        if Path(f"{db_path}{suffix}").exists()
    ]


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


def test_sqlite_create_customer_inserts_only_one_customer_and_preserves_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    existing_customer = _customer("cust-existing", "Existing Customer")
    existing_job = _job("job-existing", existing_customer.customer_id, "Existing Job")
    customer_repository.save_customer(existing_customer)
    job_repository.save_job(existing_job)
    customers_before = customer_repository.list_customers()
    jobs_before = job_repository.list_jobs()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    created_customer = CustomerRecord(
        customer_id="cust-created",
        display_name="Created Customer",
        phone="555-0102",
        email="created@example.test",
        billing_street_address="200 Synthetic Ave",
        billing_city_state_zip="Testville, WI 53000",
        notes=["Synthetic note one", "Synthetic note two"],
    )

    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=False,
    )
    created = repository.create_customer(created_customer)

    customers_after = customer_repository.list_customers()
    jobs_after = job_repository.list_jobs()
    assert created == created_customer
    assert len(customers_after) == len(customers_before) + 1
    assert customers_after[:-1] == customers_before
    assert customers_after[-1] == created_customer
    assert jobs_after == jobs_before
    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) != hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_customer_duplicate_rejects_without_database_change(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteCustomerRepository(db_path)
    original = _customer("cust-duplicate", "Original Customer")
    repository.save_customer(original)
    hash_before = _file_hash(db_path)
    schema_before = _schema_signature(db_path)

    with pytest.raises(CustomerAlreadyExistsError):
        repository.create_customer(_customer("cust-duplicate", "Replacement Attempt"))

    assert _file_hash(db_path) == hash_before
    assert repository.list_customers() == [original]
    assert _schema_signature(db_path) == schema_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_customer_rejects_read_only_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    SQLiteCustomerRepository(db_path)
    hash_before = _file_hash(db_path)
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=True,
    )

    with pytest.raises(PermissionError, match="read-only"):
        repository.create_customer(_customer("cust-created"))

    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_customer_does_not_create_nonexistent_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=False,
    )

    with pytest.raises(ValueError, match="must already exist"):
        repository.create_customer(_customer("cust-created"))

    assert not db_path.exists()
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_customer_repository_initialize_false_does_not_create_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "empty.sqlite"
    db_path.touch()

    SQLiteCustomerRepository(db_path, initialize=False, read_only=False)

    assert db_path.read_bytes() == b""


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
