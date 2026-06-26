"""Repository interfaces and in-memory implementations for customer/job records."""

from __future__ import annotations

from typing import Protocol

from phoenix_office.models.records import CustomerRecord, JobRecord


class CustomerRepository(Protocol):
    """Storage boundary for customer records."""

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        """Save or overwrite a customer record."""
        ...

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        """Return a customer record by id, or None when missing."""
        ...

    def list_customers(self) -> list[CustomerRecord]:
        """Return all customer records in insertion order."""
        ...


class JobRepository(Protocol):
    """Storage boundary for job records."""

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

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
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

    def save_job(self, record: JobRecord) -> JobRecord:
        self._jobs[record.job_id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        return [job for job in self._jobs.values() if job.customer_id == customer_id]
