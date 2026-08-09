"""Tests for in-memory customer and job repositories."""

import pytest

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    CustomerRepository,
    CustomerUpdateConflictError,
    InMemoryCustomerRepository,
    InMemoryJobRepository,
    JobAlreadyExistsError,
    JobRepository,
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


def test_customer_repository_protocol_accepts_in_memory_implementation() -> None:
    repository: CustomerRepository = InMemoryCustomerRepository()

    saved = repository.save_customer(_customer("cust-1", "Abby Hill"))

    assert repository.get_customer("cust-1") == saved


def test_save_and_get_customer() -> None:
    repository = InMemoryCustomerRepository()
    customer = _customer("cust-1", "Abby Hill")

    saved = repository.save_customer(customer)

    assert saved is customer
    assert repository.get_customer("cust-1") is customer


def test_create_customer_inserts_absent_customer() -> None:
    repository = InMemoryCustomerRepository()
    customer = _customer("cust-create", "Created Customer")

    created = repository.create_customer(customer)

    assert created is customer
    assert repository.list_customers() == [customer]


def test_create_customer_rejects_duplicate_without_overwrite() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-create", "Original Customer")
    duplicate = _customer("cust-create", "Replacement Attempt")
    repository.save_customer(original)

    with pytest.raises(CustomerAlreadyExistsError):
        repository.create_customer(duplicate)

    assert repository.get_customer("cust-create") is original
    assert repository.list_customers() == [original]


def test_get_missing_customer_returns_none() -> None:
    repository = InMemoryCustomerRepository()

    assert repository.get_customer("missing") is None


def test_saving_same_customer_id_overwrites() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-1", "Original")
    replacement = _customer("cust-1", "Replacement")

    repository.save_customer(original)
    repository.save_customer(replacement)

    assert repository.get_customer("cust-1") is replacement
    assert repository.list_customers() == [replacement]


def test_update_customer_replaces_matching_existing_customer() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-1", "Original")
    updated = _customer("cust-1", "Updated")
    repository.save_customer(original)

    result = repository.update_customer(updated, original)

    assert result is updated
    assert repository.get_customer("cust-1") is updated


def test_update_customer_rejects_missing_customer_without_creating() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-1", "Original")

    with pytest.raises(CustomerNotFoundError):
        repository.update_customer(_customer("cust-1", "Updated"), original)

    assert repository.list_customers() == []


def test_update_customer_rejects_stale_original_without_overwrite() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-1", "Original")
    newer = _customer("cust-1", "Newer")
    repository.save_customer(newer)

    with pytest.raises(CustomerUpdateConflictError):
        repository.update_customer(_customer("cust-1", "Stale Update"), original)

    assert repository.get_customer("cust-1") is newer


def test_update_customer_ignores_nonpersisted_job_fields_in_stale_token() -> None:
    repository = InMemoryCustomerRepository()
    current = CustomerRecord(
        customer_id="cust-1",
        display_name="Original",
        phone="555-0100",
        notes=["Persisted note"],
        job_street_address="100 Current Job Site",
        job_city_state_zip="Current, WI 00000",
    )
    expected_original = current.model_copy(
        update={
            "job_street_address": "200 Historical Job Site",
            "job_city_state_zip": "Historical, WI 00000",
        }
    )
    updated = current.model_copy(update={"display_name": "Updated"})
    repository.save_customer(current)

    result = repository.update_customer(updated, expected_original)

    assert result is updated
    assert repository.get_customer("cust-1") is updated


def test_update_customer_rejects_customer_id_change() -> None:
    repository = InMemoryCustomerRepository()
    original = _customer("cust-1", "Original")
    repository.save_customer(original)

    with pytest.raises(ValueError, match="customer ID cannot change"):
        repository.update_customer(_customer("cust-2", "Updated"), original)

    assert repository.list_customers() == [original]


def test_list_customers_preserves_insertion_order() -> None:
    repository = InMemoryCustomerRepository()
    first = _customer("cust-1")
    second = _customer("cust-2")
    third = _customer("cust-3")

    repository.save_customer(first)
    repository.save_customer(second)
    repository.save_customer(third)

    assert repository.list_customers() == [first, second, third]


def test_job_repository_protocol_accepts_in_memory_implementation() -> None:
    repository: JobRepository = InMemoryJobRepository()

    saved = repository.save_job(_job("job-1", "cust-1", "Tank Removal"))

    assert repository.get_job("job-1") == saved


def test_save_and_get_job() -> None:
    repository = InMemoryJobRepository()
    job = _job("job-1", "cust-1", "Tank Removal")

    saved = repository.save_job(job)

    assert saved is job
    assert repository.get_job("job-1") is job


def test_create_job_inserts_absent_job() -> None:
    repository = InMemoryJobRepository()
    job = _job("job-create", "cust-1", "Created Job")

    created = repository.create_job(job)

    assert created is job
    assert repository.list_jobs() == [job]


def test_create_job_rejects_duplicate_without_overwrite() -> None:
    repository = InMemoryJobRepository()
    original = _job("job-create", "cust-1", "Original Job")
    duplicate = _job("job-create", "cust-2", "Replacement Attempt")
    repository.save_job(original)

    with pytest.raises(JobAlreadyExistsError):
        repository.create_job(duplicate)

    assert repository.get_job("job-create") is original
    assert repository.list_jobs() == [original]


def test_get_missing_job_returns_none() -> None:
    repository = InMemoryJobRepository()

    assert repository.get_job("missing") is None


def test_saving_same_job_id_overwrites() -> None:
    repository = InMemoryJobRepository()
    original = _job("job-1", "cust-1", "Original")
    replacement = _job("job-1", "cust-1", "Replacement")

    repository.save_job(original)
    repository.save_job(replacement)

    assert repository.get_job("job-1") is replacement
    assert repository.list_jobs() == [replacement]


def test_list_jobs_preserves_insertion_order() -> None:
    repository = InMemoryJobRepository()
    first = _job("job-1", "cust-1")
    second = _job("job-2", "cust-2")
    third = _job("job-3", "cust-1")

    repository.save_job(first)
    repository.save_job(second)
    repository.save_job(third)

    assert repository.list_jobs() == [first, second, third]


def test_list_jobs_for_customer_filters_and_preserves_insertion_order() -> None:
    repository = InMemoryJobRepository()
    first = _job("job-1", "cust-1")
    other = _job("job-2", "cust-2")
    second = _job("job-3", "cust-1")

    repository.save_job(first)
    repository.save_job(other)
    repository.save_job(second)

    assert repository.list_jobs_for_customer("cust-1") == [first, second]
    assert repository.list_jobs_for_customer("cust-2") == [other]
    assert repository.list_jobs_for_customer("missing") == []


def test_repositories_are_in_memory_only() -> None:
    customer_repository = InMemoryCustomerRepository()
    job_repository = InMemoryJobRepository()

    customer_repository.save_customer(_customer("cust-1"))
    job_repository.save_job(_job("job-1", "cust-1"))

    assert customer_repository.list_customers()
    assert job_repository.list_jobs()
