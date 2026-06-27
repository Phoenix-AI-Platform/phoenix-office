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
from phoenix_office.records.proposal_adapter import (
    create_proposal_input_from_record_details,
    create_proposal_input_from_records,
)
from phoenix_office.records.proposal_details import (
    RecordProposalDetails,
    record_proposal_details_from_dict,
    record_proposal_details_from_file,
    record_proposal_details_from_json,
    record_proposal_details_to_dict,
    record_proposal_details_to_file,
    record_proposal_details_to_json,
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
from phoenix_office.records.store_files import (
    export_customer_records_file,
    export_job_records_file,
    import_customer_record_file,
    import_customer_records_file,
    import_job_record_file,
    import_job_records_file,
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
    "RecordProposalDetails",
    "RecordStore",
    "SQLiteCustomerRepository",
    "SQLiteJobRepository",
    "create_in_memory_record_store",
    "create_proposal_input_from_record_details",
    "create_proposal_input_from_records",
    "create_sqlite_record_store",
    "customer_record_from_dict",
    "customer_record_from_json",
    "customer_record_to_dict",
    "customer_record_to_json",
    "customer_records_from_json",
    "customer_records_to_json",
    "export_customer_records_file",
    "export_customer_records_json",
    "export_job_records_file",
    "export_job_records_json",
    "import_customer_record_file",
    "import_customer_record_json",
    "import_customer_records_file",
    "import_customer_records_json",
    "import_job_record_file",
    "import_job_record_json",
    "import_job_records_file",
    "import_job_records_json",
    "initialize_records_database",
    "job_record_from_dict",
    "job_record_from_json",
    "job_record_to_dict",
    "job_record_to_json",
    "job_records_from_json",
    "job_records_to_json",
    "record_proposal_details_from_dict",
    "record_proposal_details_from_file",
    "record_proposal_details_from_json",
    "record_proposal_details_to_dict",
    "record_proposal_details_to_file",
    "record_proposal_details_to_json",
]
