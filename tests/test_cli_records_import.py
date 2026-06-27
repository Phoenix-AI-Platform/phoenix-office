"""Tests for records import CLI commands."""

from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records import (
    create_sqlite_record_store,
    customer_records_to_json,
    job_records_to_json,
)

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"


def _customer(customer_id: str, display_name: str | None = None) -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name=display_name or f"Customer {customer_id}",
    )


def _job(job_id: str, customer_id: str, job_name: str | None = None) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name=job_name or f"Job {job_id}",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
    )


def test_cli_records_import_customer_and_job_examples(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"

    customer_exit_code = main(
        [
            "records",
            "import",
            "customer",
            str(CUSTOMER_EXAMPLE),
            "--db",
            str(db_path),
        ]
    )
    customer_output = capsys.readouterr()

    job_exit_code = main(
        [
            "records",
            "import",
            "job",
            str(JOB_EXAMPLE),
            "--db",
            str(db_path),
        ]
    )
    job_output = capsys.readouterr()

    store = create_sqlite_record_store(db_path)
    customer = store.customers.get_customer("customer-abby-hill")
    job = store.jobs.get_job("job-abby-hill")

    assert customer_exit_code == 0
    assert "Imported customer: customer-abby-hill" in customer_output.out
    assert job_exit_code == 0
    assert "Imported job: job-abby-hill" in job_output.out
    assert customer is not None
    assert job is not None
    assert job.customer_id == customer.customer_id


def test_cli_records_import_customer_list(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    customers = [_customer("cust-1"), _customer("cust-2")]
    input_path = tmp_path / "customers.json"
    input_path.write_text(customer_records_to_json(customers), encoding="utf-8")

    exit_code = main(
        [
            "records",
            "import",
            "customers",
            str(input_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    store = create_sqlite_record_store(db_path)
    assert exit_code == 0
    assert "Imported customers: 2" in captured.out
    assert store.customers.list_customers() == customers


def test_cli_records_import_job_list(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    jobs = [_job("job-1", "cust-1"), _job("job-2", "cust-2")]
    input_path = tmp_path / "jobs.json"
    input_path.write_text(job_records_to_json(jobs), encoding="utf-8")

    exit_code = main(
        [
            "records",
            "import",
            "jobs",
            str(input_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    store = create_sqlite_record_store(db_path)
    assert exit_code == 0
    assert "Imported jobs: 2" in captured.out
    assert store.jobs.list_jobs() == jobs


def test_cli_records_import_missing_file_fails_cleanly(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    missing_path = tmp_path / "missing.json"

    exit_code = main(
        [
            "records",
            "import",
            "customer",
            str(missing_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "record JSON file does not exist" in captured.err


def test_cli_records_import_invalid_json_fails_cleanly(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    input_path = tmp_path / "invalid.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        [
            "records",
            "import",
            "customer",
            str(input_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "failed to import records" in captured.err
    assert "Invalid record JSON" in captured.err
