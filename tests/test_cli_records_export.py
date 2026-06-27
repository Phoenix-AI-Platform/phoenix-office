"""Tests for records export CLI commands."""

from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus
from phoenix_office.records import (
    create_sqlite_record_store,
    customer_records_from_json,
    job_records_from_json,
)


def _customer(customer_id: str, display_name: str | None = None) -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name=display_name or f"Customer {customer_id}",
    )


def _job(
    job_id: str,
    customer_id: str,
    status: JobStatus = JobStatus.draft,
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name=f"Job {job_id}",
        site_street_address="123 Main St.",
        site_city_state_zip="Milwaukee, WI 53202",
        status=status,
    )


def test_cli_records_export_customers_empty_database(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "customers.json"

    exit_code = main(
        ["records", "export", "customers", str(output_path), "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert customer_records_from_json(output_path.read_text(encoding="utf-8")) == []
    assert "Exported customers: 0" in captured.out
    assert str(output_path) in captured.out


def test_cli_records_export_jobs_empty_database(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "jobs.json"

    exit_code = main(
        ["records", "export", "jobs", str(output_path), "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert job_records_from_json(output_path.read_text(encoding="utf-8")) == []
    assert "Exported jobs: 0" in captured.out
    assert str(output_path) in captured.out


def test_cli_records_export_customers_outputs_records(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "exports" / "customers.json"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer("customer-1", "Customer One"))
    store.customers.save_customer(_customer("customer-2", "Customer Two"))

    exit_code = main(
        ["records", "export", "customers", str(output_path), "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    customers = customer_records_from_json(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert [customer.customer_id for customer in customers] == ["customer-1", "customer-2"]
    assert "Exported customers: 2" in captured.out
    assert str(output_path) in captured.out


def test_cli_records_export_jobs_outputs_records(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "exports" / "jobs.json"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job("job-1", "customer-1", JobStatus.draft))
    store.jobs.save_job(_job("job-2", "customer-2", JobStatus.proposed))

    exit_code = main(
        ["records", "export", "jobs", str(output_path), "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    jobs = job_records_from_json(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert [job.job_id for job in jobs] == ["job-1", "job-2"]
    assert [job.status for job in jobs] == [JobStatus.draft, JobStatus.proposed]
    assert "Exported jobs: 2" in captured.out
    assert str(output_path) in captured.out


def test_cli_records_export_creates_parent_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "nested" / "exports" / "customers.json"

    exit_code = main(
        ["records", "export", "customers", str(output_path), "--db", str(db_path)]
    )

    assert exit_code == 0
    assert output_path.exists()


def test_cli_records_export_write_failure_returns_error(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "directory-output"
    output_path.mkdir()

    exit_code = main(
        ["records", "export", "customers", str(output_path), "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: failed to export records:" in captured.err
