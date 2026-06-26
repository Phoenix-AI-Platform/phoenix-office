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
from phoenix_office.records.store import (
    RecordStore,
    create_in_memory_record_store,
    create_sqlite_record_store,
)

__all__ = [
    "CustomerRepository",
    "InMemoryCustomerRepository",
    "InMemoryJobRepository",
    "JobRepository",
    "RecordStore",
    "SQLiteCustomerRepository",
    "SQLiteJobRepository",
    "create_in_memory_record_store",
    "create_sqlite_record_store",
    "initialize_records_database",
]
