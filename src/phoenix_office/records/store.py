"""Facade and factories for grouped customer/job record repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from phoenix_office.records.repository import (
    CustomerRepository,
    InMemoryCustomerRepository,
    InMemoryJobRepository,
    JobRepository,
)
from phoenix_office.records.sqlite import SQLiteCustomerRepository, SQLiteJobRepository


@dataclass(frozen=True)
class RecordStore:
    """Grouped access to customer and job repositories."""

    customers: CustomerRepository
    jobs: JobRepository


def create_in_memory_record_store() -> RecordStore:
    """Create a RecordStore backed by in-memory repositories."""
    return RecordStore(
        customers=InMemoryCustomerRepository(),
        jobs=InMemoryJobRepository(),
    )


def create_sqlite_record_store(db_path: Path) -> RecordStore:
    """Create a RecordStore backed by SQLite repositories sharing one database path."""
    return RecordStore(
        customers=SQLiteCustomerRepository(db_path),
        jobs=SQLiteJobRepository(db_path),
    )
