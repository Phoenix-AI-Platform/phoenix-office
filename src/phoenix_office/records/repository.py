"""Repository interfaces and in-memory implementations for Phoenix Office records."""

from typing import Protocol

from phoenix_office.models.records import CustomerRecord, JobRecord


class CustomerRepository(Protocol):
    """Protocol for customer record storage."""

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        """Save a customer record, overwriting any existing record with the same ID."""
        ...

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        """Retrieve a customer record by ID, or None if not found."""
        ...

    def list_customers(self) -> list[CustomerRecord]:
        """List all customer records, preserving insertion order."""
        ...


class JobRepository(Protocol):
    """Protocol for job record storage."""

    def save_job(self, record: JobRecord) -> JobRecord:
        """Save a job record, overwriting any existing record with the same ID."""
        ...

    def get_job(self, job_id: str) -> JobRecord | None:
        """Retrieve a job record by ID, or None if not found."""
        ...

    def list_jobs(self) -> list[JobRecord]:
        """List all job records, preserving insertion order."""
        ...

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        """List all job records for a specific customer, preserving insertion order."""
        ...


class InMemoryCustomerRepository:
    """In-memory implementation of CustomerRepository using a dict."""

    def __init__(self) -> None:
        self._store: dict[str, CustomerRecord] = {}

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        self._store[record.customer_id] = record
        return record

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        return self._store.get(customer_id)

    def list_customers(self) -> list[CustomerRecord]:
        return list(self._store.values())


class InMemoryJobRepository:
    """In-memory implementation of JobRepository using a dict."""

    def __init__(self) -> None:
        self._store: dict[str, JobRecord] = {}

    def save_job(self, record: JobRecord) -> JobRecord:
        self._store[record.job_id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._store.get(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return list(self._store.values())

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        return [job for job in self._store.values() if job.customer_id == customer_id]
