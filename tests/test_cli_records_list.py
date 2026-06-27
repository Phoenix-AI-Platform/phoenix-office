"""Tests for records list CLI commands."""

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus
from phoenix_office.records import create_sqlite_record_store


def _customer(customer_id: str = "customer-abby-hill") -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name="Abby Hill",
    )


def _job(job_id: str = "job-abby-hill", customer_id: str = "customer-abby-hill") -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name="Abby Hill tank removal proposal",
        site_street_address="123 Main St.",
        site_city_state_zip="Menomonee Falls, WI 53051",
        status=JobStatus.draft,
    )


def test_cli_records_list_customers_empty_database(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"

    exit_code = main(["records", "list", "customers", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No customers found." in captured.out


def test_cli_records_list_jobs_empty_database(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"

    exit_code = main(["records", "list", "jobs", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No jobs found." in captured.out


def test_cli_records_list_customers_outputs_text(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer())

    exit_code = main(["records", "list", "customers", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "customer-abby-hill" in captured.out
    assert "Abby Hill" in captured.out


def test_cli_records_list_jobs_outputs_text(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job())

    exit_code = main(["records", "list", "jobs", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "job-abby-hill" in captured.out
    assert "customer-abby-hill" in captured.out
    assert "Abby Hill tank removal proposal" in captured.out
    assert "draft" in captured.out


def test_cli_records_list_customers_json_output(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer())

    exit_code = main(["records", "list", "customers", "--db", str(db_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload[0]["customer_id"] == "customer-abby-hill"


def test_cli_records_list_jobs_json_output(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job())

    exit_code = main(["records", "list", "jobs", "--db", str(db_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload[0]["job_id"] == "job-abby-hill"
    assert payload[0]["status"] == "draft"
