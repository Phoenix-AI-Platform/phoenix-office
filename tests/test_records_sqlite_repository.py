"""Tests for SQLite customer and job repositories."""

import hashlib
import inspect
import sqlite3
from pathlib import Path

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType
from phoenix_office.records import (
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    CustomerUpdateConflictError,
    JobAlreadyExistsError,
    JobNotFoundError,
    JobUpdateConflictError,
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


def test_sqlite_update_customer_changes_only_one_existing_customer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    original = CustomerRecord(
        customer_id="cust-a",
        display_name="Original Customer",
        phone="555-0100",
        notes=["Original note"],
    )
    other = _customer("cust-b", "Other Customer")
    jobs = (
        _job("job-a", "cust-a", "Customer A Job"),
        _job("job-b", "cust-b", "Customer B Job"),
    )
    customer_repository.save_customer(original)
    customer_repository.save_customer(other)
    for job in jobs:
        job_repository.save_job(job)
    customers_before = customer_repository.list_customers()
    jobs_before = job_repository.list_jobs()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    updated = CustomerRecord(
        customer_id="cust-a",
        display_name="Updated Customer",
        phone=None,
        email="updated@example.test",
        billing_street_address="400 Synthetic Ave.",
        billing_city_state_zip="Example, WI 00000",
        notes=["Updated note"],
    )
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=False,
    )

    result = repository.update_customer(updated, original)

    customers_after = customer_repository.list_customers()
    assert result is updated
    assert len(customers_after) == len(customers_before)
    assert customers_after == [updated, other]
    assert job_repository.list_jobs() == jobs_before
    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) != hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_customer_rejects_stale_original_without_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    original = _customer("cust-a", "Original Customer")
    newer = _customer("cust-a", "Newer Customer")
    job = _job("job-a", "cust-a", "Existing Job")
    repository.save_customer(original)
    job_repository.save_job(job)
    repository.save_customer(newer)
    hash_before = _file_hash(db_path)
    schema_before = _schema_signature(db_path)
    jobs_before = job_repository.list_jobs()

    with pytest.raises(CustomerUpdateConflictError):
        repository.update_customer(_customer("cust-a", "Stale Update"), original)

    assert repository.get_customer("cust-a") == newer
    assert _file_hash(db_path) == hash_before
    assert _schema_signature(db_path) == schema_before
    assert job_repository.list_jobs() == jobs_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_customer_ignores_nonpersisted_job_fields_in_stale_token(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteCustomerRepository(db_path)
    persisted = _customer("cust-a", "Original Customer")
    repository.save_customer(persisted)
    expected = persisted.model_copy(
        update={
            "job_street_address": "Not a persisted concurrency value",
            "job_city_state_zip": "Example, WI 00000",
        }
    )
    updated = _customer("cust-a", "Updated Customer")

    repository.update_customer(updated, expected)

    assert repository.get_customer("cust-a") == updated


def test_sqlite_update_customer_rejects_missing_without_recreation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    original = _customer("cust-a", "Original Customer")
    job = _job("job-a", "cust-a", "Existing Job")
    repository.save_customer(original)
    job_repository.save_job(job)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM customers WHERE customer_id = ?", ("cust-a",))
        connection.commit()
    hash_before = _file_hash(db_path)
    jobs_before = job_repository.list_jobs()

    with pytest.raises(CustomerNotFoundError):
        repository.update_customer(_customer("cust-a", "Updated Customer"), original)

    assert repository.get_customer("cust-a") is None
    assert _file_hash(db_path) == hash_before
    assert job_repository.list_jobs() == jobs_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_customer_rejects_customer_id_change(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteCustomerRepository(db_path)
    original = _customer("cust-a", "Original Customer")
    repository.save_customer(original)
    hash_before = _file_hash(db_path)

    with pytest.raises(ValueError, match="customer ID cannot change"):
        repository.update_customer(_customer("cust-b", "Updated Customer"), original)

    assert repository.list_customers() == [original]
    assert _file_hash(db_path) == hash_before


def test_sqlite_update_customer_rejects_read_only_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    writable = SQLiteCustomerRepository(db_path)
    original = _customer("cust-a", "Original Customer")
    writable.save_customer(original)
    hash_before = _file_hash(db_path)
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=True,
    )

    with pytest.raises(PermissionError, match="read-only"):
        repository.update_customer(_customer("cust-a", "Updated Customer"), original)

    assert _file_hash(db_path) == hash_before


def test_sqlite_update_customer_does_not_create_nonexistent_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=False,
    )
    original = _customer("cust-a", "Original Customer")

    with pytest.raises(ValueError, match="must already exist"):
        repository.update_customer(_customer("cust-a", "Updated Customer"), original)

    assert not db_path.exists()


def test_sqlite_update_customer_rejects_missing_table_without_initialization(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "empty.sqlite"
    db_path.touch()
    bytes_before = db_path.read_bytes()
    repository = SQLiteCustomerRepository(
        db_path,
        initialize=False,
        read_only=False,
    )
    original = _customer("cust-a", "Original Customer")

    with pytest.raises(ValueError, match="not usable for customer updates"):
        repository.update_customer(_customer("cust-a", "Updated Customer"), original)

    assert db_path.read_bytes() == bytes_before


def test_sqlite_update_customer_uses_plain_update_only() -> None:
    source = inspect.getsource(SQLiteCustomerRepository.update_customer)

    assert "UPDATE customers" in source
    assert "INSERT" not in source
    assert "ON CONFLICT" not in source
    assert "save_customer" not in source


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


def test_sqlite_create_job_inserts_only_authorized_row_and_preserves_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    customer_a = _customer("cust-a", "Synthetic Customer A")
    customer_b = _customer("cust-b", "Synthetic Customer B")
    existing_a = _job("job-a", customer_a.customer_id, "Existing Job A")
    existing_b = _job("job-b", customer_b.customer_id, "Existing Job B")
    customer_repository.save_customer(customer_a)
    customer_repository.save_customer(customer_b)
    job_repository.save_job(existing_a)
    job_repository.save_job(existing_b)
    customers_before = customer_repository.list_customers()
    jobs_before = job_repository.list_jobs()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    created_job = JobRecord(
        job_id="job-created",
        customer_id=customer_a.customer_id,
        job_name="Created Synthetic Job",
        site_street_address="300 Synthetic Ave",
        site_city_state_zip="Testville, WI 53000",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=1000,
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes=["Explicit synthetic scope"],
        internal_notes=["Explicit synthetic internal note"],
    )

    repository = SQLiteJobRepository(
        db_path,
        initialize=False,
        read_only=False,
    )
    created = repository.create_job(created_job)

    customers_after = customer_repository.list_customers()
    jobs_after = job_repository.list_jobs()
    assert created == created_job
    assert customers_after == customers_before
    assert len(jobs_after) == len(jobs_before) + 1
    assert jobs_after[:-1] == jobs_before
    assert jobs_after[-1] == created_job
    assert job_repository.list_jobs_for_customer(customer_a.customer_id) == [
        existing_a,
        created_job,
    ]
    assert job_repository.list_jobs_for_customer(customer_b.customer_id) == [
        existing_b
    ]
    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) != hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_job_duplicate_rejects_without_database_change(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    repository = SQLiteJobRepository(db_path, initialize=False)
    customer_repository.save_customer(_customer("cust-a"))
    customer_repository.save_customer(_customer("cust-b"))
    original = _job("job-duplicate", "cust-a", "Original Job")
    repository.save_job(original)
    customers_before = customer_repository.list_customers()
    jobs_before = repository.list_jobs()
    hash_before = _file_hash(db_path)
    schema_before = _schema_signature(db_path)

    with pytest.raises(JobAlreadyExistsError):
        repository.create_job(
            _job("job-duplicate", "cust-b", "Replacement Attempt")
        )

    assert _file_hash(db_path) == hash_before
    assert customer_repository.list_customers() == customers_before
    assert repository.list_jobs() == jobs_before
    assert repository.get_job(original.job_id) == original
    assert _schema_signature(db_path) == schema_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_job_rejects_read_only_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    SQLiteJobRepository(db_path)
    hash_before = _file_hash(db_path)
    repository = SQLiteJobRepository(
        db_path,
        initialize=False,
        read_only=True,
    )

    with pytest.raises(PermissionError, match="read-only"):
        repository.create_job(_job("job-created", "cust-a"))

    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_job_does_not_create_nonexistent_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"
    repository = SQLiteJobRepository(
        db_path,
        initialize=False,
        read_only=False,
    )

    with pytest.raises(ValueError, match="must already exist"):
        repository.create_job(_job("job-created", "cust-a"))

    assert not db_path.exists()
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_create_job_rejects_missing_jobs_table_without_initialization(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "customers-only.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE customers (customer_id TEXT PRIMARY KEY)"
        )
        connection.commit()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    repository = SQLiteJobRepository(
        db_path,
        initialize=False,
        read_only=False,
    )

    with pytest.raises(ValueError, match="not usable"):
        repository.create_job(_job("job-created", "cust-a"))

    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_job_repository_initialize_false_does_not_create_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "empty.sqlite"
    db_path.touch()

    SQLiteJobRepository(db_path, initialize=False, read_only=False)

    assert db_path.read_bytes() == b""


def test_sqlite_update_job_changes_exactly_one_existing_job(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    job_repository = SQLiteJobRepository(db_path, initialize=False)
    customer_a = _customer("cust-a", "Synthetic Customer A")
    customer_b = _customer("cust-b", "Synthetic Customer B")
    job_a1 = _job("job-a1", "cust-a", "Original Job A1")
    job_a2 = _job("job-a2", "cust-a", "Original Job A2")
    job_b1 = _job("job-b1", "cust-b", "Original Job B1")
    for customer in (customer_a, customer_b):
        customer_repository.save_customer(customer)
    for job in (job_a1, job_a2, job_b1):
        job_repository.save_job(job)
    customers_before = customer_repository.list_customers()
    jobs_before = job_repository.list_jobs()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    updated = JobRecord(
        job_id=job_a1.job_id,
        customer_id=job_a1.customer_id,
        job_name="Updated Synthetic Job A1",
        site_street_address="500 Synthetic Ave",
        site_city_state_zip="Testville, WI 53000",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=1200,
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes=["Updated explicit scope"],
        internal_notes=["Updated explicit internal note"],
    )

    result = SQLiteJobRepository(
        db_path,
        initialize=False,
        read_only=False,
    ).update_job(updated, job_a1)

    jobs_after = job_repository.list_jobs()
    assert result == updated
    assert job_repository.get_job(job_a1.job_id) == updated
    assert customer_repository.list_customers() == customers_before
    assert len(jobs_after) == len(jobs_before)
    assert jobs_after[1:] == jobs_before[1:]
    assert updated.customer_id == job_a1.customer_id
    assert job_repository.list_jobs_for_customer("cust-a") == [updated, job_a2]
    assert job_repository.list_jobs_for_customer("cust-b") == [job_b1]
    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) != hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_job_rejects_stale_original_without_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteJobRepository(db_path)
    original = _job("job-1", "cust-1", "Original")
    newer = original.model_copy(update={"job_name": "Newer"})
    attempted = original.model_copy(update={"job_name": "Stale Attempt"})
    repository.save_job(original)
    repository.save_job(newer)
    hash_before = _file_hash(db_path)
    schema_before = _schema_signature(db_path)

    with pytest.raises(JobUpdateConflictError):
        repository.update_job(attempted, original)

    assert repository.get_job("job-1") == newer
    assert _file_hash(db_path) == hash_before
    assert _schema_signature(db_path) == schema_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_job_rejects_missing_without_recreation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(db_path)
    repository = SQLiteJobRepository(db_path, initialize=False)
    customer = _customer("cust-1")
    original = _job("job-1", customer.customer_id, "Original")
    other = _job("job-2", customer.customer_id, "Other")
    customer_repository.save_customer(customer)
    repository.save_job(original)
    repository.save_job(other)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM jobs WHERE job_id = ?", (original.job_id,))
        connection.commit()
    customers_before = customer_repository.list_customers()
    jobs_before = repository.list_jobs()
    hash_before = _file_hash(db_path)

    with pytest.raises(JobNotFoundError):
        repository.update_job(
            original.model_copy(update={"job_name": "Recreate Attempt"}),
            original,
        )

    assert repository.get_job(original.job_id) is None
    assert repository.list_jobs() == jobs_before
    assert customer_repository.list_customers() == customers_before
    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


@pytest.mark.parametrize("identity", ["job_id", "customer_id"])
def test_sqlite_update_job_rejects_identity_changes_without_mutation(
    tmp_path: Path,
    identity: str,
) -> None:
    db_path = tmp_path / "records.sqlite"
    repository = SQLiteJobRepository(db_path)
    original = _job("job-1", "cust-1", "Original")
    repository.save_job(original)
    attempted = original.model_copy(update={identity: f"changed-{identity}"})
    hash_before = _file_hash(db_path)

    with pytest.raises(ValueError, match="cannot change"):
        repository.update_job(attempted, original)

    assert repository.get_job("job-1") == original
    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_job_rejects_read_only_repository(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    writable = SQLiteJobRepository(db_path)
    original = _job("job-1", "cust-1", "Original")
    writable.save_job(original)
    hash_before = _file_hash(db_path)
    repository = SQLiteJobRepository(db_path, initialize=False, read_only=True)

    with pytest.raises(PermissionError, match="read-only"):
        repository.update_job(
            original.model_copy(update={"job_name": "Updated"}),
            original,
        )

    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_job_does_not_create_nonexistent_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"
    original = _job("job-1", "cust-1", "Original")
    repository = SQLiteJobRepository(db_path, initialize=False, read_only=False)

    with pytest.raises(ValueError, match="must already exist"):
        repository.update_job(
            original.model_copy(update={"job_name": "Updated"}),
            original,
        )

    assert not db_path.exists()
    assert _sqlite_sidecars(db_path) == []


def test_sqlite_update_job_rejects_missing_table_without_initialization(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "customers-only.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE customers (customer_id TEXT PRIMARY KEY)")
        connection.commit()
    schema_before = _schema_signature(db_path)
    hash_before = _file_hash(db_path)
    original = _job("job-1", "cust-1", "Original")
    repository = SQLiteJobRepository(db_path, initialize=False, read_only=False)

    with pytest.raises(ValueError, match="not usable"):
        repository.update_job(
            original.model_copy(update={"job_name": "Updated"}),
            original,
        )

    assert _schema_signature(db_path) == schema_before
    assert _file_hash(db_path) == hash_before
    assert _sqlite_sidecars(db_path) == []


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
