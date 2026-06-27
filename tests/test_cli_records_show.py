"""Tests for records show CLI commands."""

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.records import (
    CustomerRecord,
    JobRecord,
    JobStatus,
    TankLocationType,
)
from phoenix_office.records import create_sqlite_record_store


def _customer(customer_id: str = "customer-abby-hill") -> CustomerRecord:
    return CustomerRecord(
        customer_id=customer_id,
        display_name="Abby Hill",
        phone="555-0100",
        email="abby@example.com",
        billing_street_address="123 Main St.",
        billing_city_state_zip="Menomonee Falls, WI 53051",
        notes=["Prefers email."],
    )


def _job(
    job_id: str = "job-abby-hill",
    customer_id: str = "customer-abby-hill",
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name="Abby Hill tank removal proposal",
        site_street_address="123 Main St.",
        site_city_state_zip="Menomonee Falls, WI 53051",
        status=JobStatus.proposed,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=550,
        tank_contents="fuel oil",
        contents_known=True,
        scope_notes=["Remove existing tank."],
        internal_notes=["Confirm access before scheduling."],
    )


def test_cli_records_show_customer_outputs_text(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer())

    exit_code = main(
        ["records", "show", "customer", "customer-abby-hill", "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "customer-abby-hill" in captured.out
    assert "Abby Hill" in captured.out
    assert "555-0100" in captured.out
    assert "abby@example.com" in captured.out
    assert "Prefers email." in captured.out


def test_cli_records_show_job_outputs_text(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job())

    exit_code = main(["records", "show", "job", "job-abby-hill", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "job-abby-hill" in captured.out
    assert "customer-abby-hill" in captured.out
    assert "Abby Hill tank removal proposal" in captured.out
    assert "proposed" in captured.out
    assert "underground" in captured.out
    assert "fuel oil" in captured.out


def test_cli_records_show_customer_json_output(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer())

    exit_code = main(
        [
            "records",
            "show",
            "customer",
            "customer-abby-hill",
            "--db",
            str(db_path),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["customer_id"] == "customer-abby-hill"


def test_cli_records_show_job_json_output(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job())

    exit_code = main(
        [
            "records",
            "show",
            "job",
            "job-abby-hill",
            "--db",
            str(db_path),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["job_id"] == "job-abby-hill"
    assert payload["status"] == "proposed"


def test_cli_records_show_missing_customer_returns_error(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.customers.save_customer(_customer())

    exit_code = main(
        ["records", "show", "customer", "missing-customer", "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Customer not found: missing-customer" in captured.err


def test_cli_records_show_missing_job_returns_error(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    store = create_sqlite_record_store(db_path)
    store.jobs.save_job(_job())

    exit_code = main(["records", "show", "job", "missing-job", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Job not found: missing-job" in captured.err


def test_cli_records_show_customer_empty_database_behaves_as_missing(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"

    exit_code = main(
        ["records", "show", "customer", "customer-abby-hill", "--db", str(db_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Customer not found: customer-abby-hill" in captured.err


def test_cli_records_show_job_empty_database_behaves_as_missing(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"

    exit_code = main(["records", "show", "job", "job-abby-hill", "--db", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Job not found: job-abby-hill" in captured.err
