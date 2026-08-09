"""Repository interfaces and in-memory implementations for customer/job records."""

from __future__ import annotations

from typing import Protocol

from phoenix_office.models.records import CustomerRecord, JobRecord


class CustomerAlreadyExistsError(ValueError):
    """A create-only customer insert found an existing customer id."""


class CustomerNotFoundError(ValueError):
    """A guarded customer update found that the original customer is missing."""


class CustomerUpdateConflictError(ValueError):
    """A guarded customer update found newer persisted customer values."""


class JobAlreadyExistsError(ValueError):
    """A create-only job insert found an existing job id."""


class CustomerRepository(Protocol):
    """Storage boundary for customer records."""

    def create_customer(self, record: CustomerRecord) -> CustomerRecord:
        """Insert a new customer without overwriting an existing id."""
        ...

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        """Save or overwrite a customer record."""
        ...

    def update_customer(
        self,
        record: CustomerRecord,
        expected_original: CustomerRecord,
    ) -> CustomerRecord:
        """Update one unchanged existing customer without creating it."""
        ...

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        """Return a customer record by id, or None when missing."""
        ...

    def list_customers(self) -> list[CustomerRecord]:
        """Return all customer records in insertion order."""
        ...


class JobRepository(Protocol):
    """Storage boundary for job records."""

    def create_job(self, record: JobRecord) -> JobRecord:
        """Insert a new job without overwriting an existing id."""
        ...

    def save_job(self, record: JobRecord) -> JobRecord:
        """Save or overwrite a job record."""
        ...

    def get_job(self, job_id: str) -> JobRecord | None:
        """Return a job record by id, or None when missing."""
        ...

    def list_jobs(self) -> list[JobRecord]:
        """Return all job records in insertion order."""
        ...

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        """Return jobs for a customer in insertion order."""
        ...


class InMemoryCustomerRepository:
    """In-memory CustomerRepository implementation for tests and early workflows."""

    def __init__(self) -> None:
        self._customers: dict[str, CustomerRecord] = {}

    def create_customer(self, record: CustomerRecord) -> CustomerRecord:
        if record.customer_id in self._customers:
            raise CustomerAlreadyExistsError(
                "Customer ID already exists; no customer was changed."
            )
        self._customers[record.customer_id] = record
        return record

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        self._customers[record.customer_id] = record
        return record

    def update_customer(
        self,
        record: CustomerRecord,
        expected_original: CustomerRecord,
    ) -> CustomerRecord:
        if record.customer_id != expected_original.customer_id:
            raise ValueError("customer ID cannot change during an update")
        current = self._customers.get(record.customer_id)
        if current is None:
            raise CustomerNotFoundError(
                "Customer no longer exists; reload customers before retrying."
            )
        if current != expected_original:
            raise CustomerUpdateConflictError(
                "Customer changed elsewhere; reload customers before retrying."
            )
        self._customers[record.customer_id] = record
        return record

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        return self._customers.get(customer_id)

    def list_customers(self) -> list[CustomerRecord]:
        return list(self._customers.values())


class InMemoryJobRepository:
    """In-memory JobRepository implementation for tests and early workflows."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create_job(self, record: JobRecord) -> JobRecord:
        if record.job_id in self._jobs:
            raise JobAlreadyExistsError(
                "Job ID already exists; no job was changed."
            )
        self._jobs[record.job_id] = record
        return record

    def save_job(self, record: JobRecord) -> JobRecord:
        self._jobs[record.job_id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        return [job for job in self._jobs.values() if job.customer_id == customer_id]
