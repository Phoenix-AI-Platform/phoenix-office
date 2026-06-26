"""Repository interfaces and implementations for Phoenix Office records."""

from phoenix_office.records.repository import (
    CustomerRepository,
    InMemoryCustomerRepository,
    InMemoryJobRepository,
    JobRepository,
)
from phoenix_office.records.sqlite import (
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    initialize_records_database,
)

__all__ = [
    "CustomerRepository",
    "InMemoryCustomerRepository",
    "InMemoryJobRepository",
    "JobRepository",
    "SQLiteCustomerRepository",
    "SQLiteJobRepository",
    "initialize_records_database",
]
