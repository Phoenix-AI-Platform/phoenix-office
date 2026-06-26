"""Tests for record JSON example fixtures."""

import json
from pathlib import Path

from phoenix_office.models.records import JobStatus, TankLocationType
from phoenix_office.records import (
    customer_record_from_json,
    customer_record_to_json,
    job_record_from_json,
    job_record_to_json,
)

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"
EXAMPLES_README = ROOT / "examples" / "README.md"


def test_record_example_files_exist() -> None:
    assert CUSTOMER_EXAMPLE.exists()
    assert JOB_EXAMPLE.exists()


def test_customer_example_loads_through_json_codec() -> None:
    customer = customer_record_from_json(CUSTOMER_EXAMPLE.read_text(encoding="utf-8"))

    assert customer.customer_id == "customer-abby-hill"
    assert customer.display_name == "Abby Hill"
    assert customer.notes == []


def test_job_example_loads_through_json_codec() -> None:
    job = job_record_from_json(JOB_EXAMPLE.read_text(encoding="utf-8"))

    assert job.job_id == "job-abby-hill"
    assert job.customer_id == "customer-abby-hill"
    assert job.status == JobStatus.draft
    assert job.tank_location_type == TankLocationType.unknown


def test_job_example_customer_id_matches_customer_example() -> None:
    customer = customer_record_from_json(CUSTOMER_EXAMPLE.read_text(encoding="utf-8"))
    job = job_record_from_json(JOB_EXAMPLE.read_text(encoding="utf-8"))

    assert job.customer_id == customer.customer_id


def test_record_examples_serialize_back_to_valid_json() -> None:
    customer = customer_record_from_json(CUSTOMER_EXAMPLE.read_text(encoding="utf-8"))
    job = job_record_from_json(JOB_EXAMPLE.read_text(encoding="utf-8"))

    serialized_customer = json.loads(customer_record_to_json(customer))
    serialized_job = json.loads(job_record_to_json(job))

    assert serialized_customer["customer_id"] == "customer-abby-hill"
    assert serialized_job["job_id"] == "job-abby-hill"


def test_record_examples_are_mentioned_in_examples_readme() -> None:
    readme = EXAMPLES_README.read_text(encoding="utf-8")

    assert "examples/records/customer_abby_hill.json" in readme
    assert "examples/records/job_abby_hill.json" in readme
