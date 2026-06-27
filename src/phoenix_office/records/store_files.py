"""File-based JSON import/export helpers for RecordStore instances."""

from __future__ import annotations

from pathlib import Path

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records.store import RecordStore
from phoenix_office.records.store_json import (
    export_customer_records_json,
    export_job_records_json,
    import_customer_record_json,
    import_customer_records_json,
    import_job_record_json,
    import_job_records_json,
)


def import_customer_record_file(store: RecordStore, path: Path) -> CustomerRecord:
    """Read one customer record JSON file and import it into the store."""
    return import_customer_record_json(store, path.read_text(encoding="utf-8"))


def import_job_record_file(store: RecordStore, path: Path) -> JobRecord:
    """Read one job record JSON file and import it into the store."""
    return import_job_record_json(store, path.read_text(encoding="utf-8"))


def import_customer_records_file(store: RecordStore, path: Path) -> list[CustomerRecord]:
    """Read a customer records JSON file and import all records into the store."""
    return import_customer_records_json(store, path.read_text(encoding="utf-8"))


def import_job_records_file(store: RecordStore, path: Path) -> list[JobRecord]:
    """Read a job records JSON file and import all records into the store."""
    return import_job_records_json(store, path.read_text(encoding="utf-8"))


def export_customer_records_file(store: RecordStore, path: Path) -> Path:
    """Export customer records from the store to a UTF-8 JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_customer_records_json(store), encoding="utf-8")
    return path


def export_job_records_file(store: RecordStore, path: Path) -> Path:
    """Export job records from the store to a UTF-8 JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_job_records_json(store), encoding="utf-8")
    return path
