"""Repository interfaces and implementations for Phoenix Office records."""

from phoenix_office.records.repository import (
    CustomerRepository,
    InMemoryCustomerRepository,
    InMemoryJobRepository,
    JobRepository,
)

__all__ = [
    "CustomerRepository",
    "InMemoryCustomerRepository",
    "InMemoryJobRepository",
    "JobRepository",
]
