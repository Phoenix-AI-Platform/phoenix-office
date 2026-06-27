"""Tests for records list CLI commands."""

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.records import create_sqlite_record_store


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
    store.customers.save_customer(
        type(store.customers.get_customer)(  # type: ignore[misc]
        )
    )
