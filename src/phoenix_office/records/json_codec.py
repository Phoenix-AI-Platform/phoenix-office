"""JSON serialization helpers for Phoenix Office customer and job records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.models.records import CustomerRecord, JobRecord


def customer_record_to_dict(record: CustomerRecord) -> dict[str, object]:
    """Convert a customer record to a JSON-ready dictionary."""
    return record.model_dump(mode="json")


def customer_record_from_dict(data: dict[str, object]) -> CustomerRecord:
    """Build a customer record from a dictionary."""
    return CustomerRecord.model_validate(data)


def customer_record_to_json(record: CustomerRecord) -> str:
    """Convert a customer record to deterministic JSON text."""
    return _to_json(customer_record_to_dict(record))


def customer_record_from_json(value: str) -> CustomerRecord:
    """Build a customer record from JSON text."""
    return customer_record_from_dict(_load_json_object(value))


def customer_record_from_json_file(path: Path) -> CustomerRecord:
    """Load a customer record from an explicit UTF-8 JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Customer record JSON file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Customer record JSON path is not a file: {path}")
    return customer_record_from_json(path.read_text(encoding="utf-8"))


def job_record_to_dict(record: JobRecord) -> dict[str, object]:
    """Convert a job record to a JSON-ready dictionary."""
    return record.model_dump(mode="json")


def job_record_from_dict(data: dict[str, object]) -> JobRecord:
    """Build a job record from a dictionary."""
    return JobRecord.model_validate(data)


def job_record_to_json(record: JobRecord) -> str:
    """Convert a job record to deterministic JSON text."""
    return _to_json(job_record_to_dict(record))


def job_record_from_json(value: str) -> JobRecord:
    """Build a job record from JSON text."""
    return job_record_from_dict(_load_json_object(value))


def customer_records_to_json(records: list[CustomerRecord]) -> str:
    """Convert customer records to deterministic JSON text."""
    return _to_json([customer_record_to_dict(record) for record in records])


def customer_records_from_json(value: str) -> list[CustomerRecord]:
    """Build customer records from JSON text containing a list."""
    return [customer_record_from_dict(item) for item in _load_json_object_list(value)]


def job_records_to_json(records: list[JobRecord]) -> str:
    """Convert job records to deterministic JSON text."""
    return _to_json([job_record_to_dict(record) for record in records])


def job_records_from_json(value: str) -> list[JobRecord]:
    """Build job records from JSON text containing a list."""
    return [job_record_from_dict(item) for item in _load_json_object_list(value)]


def _to_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _load_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid record JSON: {exc.msg}") from exc


def _load_json_object(value: str) -> dict[str, object]:
    data = _load_json(value)
    if not isinstance(data, dict):
        raise ValueError("Record JSON must be an object.")
    return data


def _load_json_object_list(value: str) -> list[dict[str, object]]:
    data = _load_json(value)
    if not isinstance(data, list):
        raise ValueError("Record JSON must be a list.")

    records: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Record JSON list items must be objects.")
        records.append(item)
    return records
