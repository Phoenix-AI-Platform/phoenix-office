"""JSON import/export helpers for RecordStore instances."""

from __future__ import annotations

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records.json_codec import (
    customer_record_from_json,
    customer_records_from_json,
    customer_records_to_json,
    job_record_from_json,
    job_records_from_json,
    job_records_to_json,
)
from phoenix_office.records.store import RecordStore


def import_customer_record_json(store: RecordStore, value: str) -> CustomerRecord:
    """Parse one customer record JSON document and save it into the store."""
    return store.customers.save_customer(customer_record_from_json(value))


def import_job_record_json(store: RecordStore, value: str) -> JobRecord:
    """Parse one job record JSON document and save it into the store."""
    return store.jobs.save_job(job_record_from_json(value))


def import_customer_records_json(store: RecordStore, value: str) -> list[CustomerRecord]:
    """Parse customer record JSON array text and save each record into the store."""
    return [store.customers.save_customer(record) for record in customer_records_from_json(value)]


def import_job_records_json(store: RecordStore, value: str) -> list[JobRecord]:
    """Parse job record JSON array text and save each record into the store."""
    return [store.jobs.save_job(record) for record in job_records_from_json(value)]


def export_customer_records_json(store: RecordStore) -> str:
    """Serialize all customer records from the store to JSON array text."""
    return customer_records_to_json(store.customers.list_customers())


def export_job_records_json(store: RecordStore) -> str:
    """Serialize all job records from the store to JSON array text."""
    return job_records_to_json(store.jobs.list_jobs())
