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
from phoenix_office.records.store_json import (
    export_customer_records_json,
    export_job_records_json,
    import_customer_record_json,
    import_customer_records_json,
    import_job_record_json,
    import_job_records_json,
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
    "export_customer_records_json",
    "export_job_records_json",
    "import_customer_record_json",
    "import_customer_records_json",
    "import_job_record_json",
    "import_job_records_json",
    "initialize_records_database",
    "job_record_from_dict",
    "job_record_from_json",
    "job_record_to_dict",
    "job_record_to_json",
    "job_records_from_json",
    "job_records_to_json",
]
