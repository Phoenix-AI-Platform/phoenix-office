"""Repository interfaces and implementations for Phoenix Office records."""

from phoenix_office.records.json_codec import (
    customer_record_from_dict,
    customer_record_from_json,
    customer_record_to_dict,
    customer_record_to_json,
    customer_records_from_json,
    customer_records_to_json,
    job_record_from_dict,
    job_record_from_json,
    job_record_to_dict,
    job_record_to_json,
    job_records_from_json,
    job_records_to_json,
)
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
    "customer_record_from_dict",
    "customer_record_from_json",
    "customer_record_to_dict",
    "customer_record_to_json",
    "customer_records_from_json",
    "customer_records_to_json",
    "initialize_records_database",
    "job_record_from_dict",
    "job_record_from_json",
    "job_record_to_dict",
    "job_record_to_json",
    "job_records_from_json",
    "job_records_to_json",
]
