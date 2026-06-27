"""Tests for records proposal-input CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput
from phoenix_office.records import (
    create_sqlite_record_store,
    import_customer_record_file,
    import_job_record_file,
    record_proposal_details_from_file,
)

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"
DETAILS_EXAMPLE = ROOT / "examples" / "records" / "proposal_details_abby_hill.json"


def _seed_customer_and_job(db_path: Path) -> None:
    store = create_sqlite_record_store(db_path)
    import_customer_record_file(store, CUSTOMER_EXAMPLE)
    import_job_record_file(store, JOB_EXAMPLE)


def test_cli_records_proposal_input_composes_json(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "nested" / "proposal_input.json"
    _seed_customer_and_job(db_path)

    exit_code = main(
        [
            "records",
            "proposal-input",
            "customer-abby-hill",
            "job-abby-hill",
            str(DETAILS_EXAMPLE),
            str(output_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    output_text = output_path.read_text(encoding="utf-8")
    proposal = ProposalInput.model_validate(json.loads(output_text))
    details = record_proposal_details_from_file(DETAILS_EXAMPLE)

    assert exit_code == 0
    assert output_path.exists()
    assert output_text.endswith("\n")
    assert output_text.splitlines()[1].startswith('  "city_state_zip"')
    assert "Composed proposal input JSON" in captured.out
    assert str(output_path) in captured.out
    assert proposal.customer_name == "Abby Hill"
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Menomonee Falls, WI 53051"
    assert proposal.proposal_date == details.proposal_date
    assert proposal.item_description == details.item_description
    assert proposal.scope_items == details.scope_items
    assert proposal.pricing == details.pricing
    assert proposal.notes == details.notes
    assert proposal.company_config == details.company_config


def test_cli_records_proposal_input_missing_customer_returns_error(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "proposal_input.json"
    store = create_sqlite_record_store(db_path)
    import_job_record_file(store, JOB_EXAMPLE)

    exit_code = main(
        [
            "records",
            "proposal-input",
            "missing-customer",
            "job-abby-hill",
            str(DETAILS_EXAMPLE),
            str(output_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Customer not found: missing-customer" in captured.err
    assert not output_path.exists()


def test_cli_records_proposal_input_missing_job_returns_error(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    output_path = tmp_path / "proposal_input.json"
    store = create_sqlite_record_store(db_path)
    import_customer_record_file(store, CUSTOMER_EXAMPLE)

    exit_code = main(
        [
            "records",
            "proposal-input",
            "customer-abby-hill",
            "missing-job",
            str(DETAILS_EXAMPLE),
            str(output_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Job not found: missing-job" in captured.err
    assert not output_path.exists()


def test_cli_records_proposal_input_invalid_details_json_returns_error(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    details_path = tmp_path / "invalid_details.json"
    output_path = tmp_path / "proposal_input.json"
    details_path.write_text("{not valid json", encoding="utf-8")
    _seed_customer_and_job(db_path)

    exit_code = main(
        [
            "records",
            "proposal-input",
            "customer-abby-hill",
            "job-abby-hill",
            str(details_path),
            str(output_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: failed to compose proposal input:" in captured.err
    assert "Invalid record proposal details JSON" in captured.err
    assert not output_path.exists()


def test_cli_records_proposal_input_invalid_details_data_returns_error(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    details_path = tmp_path / "invalid_details_data.json"
    output_path = tmp_path / "proposal_input.json"
    payload = json.loads(DETAILS_EXAMPLE.read_text(encoding="utf-8"))
    payload["scope_items"] = []
    details_path.write_text(json.dumps(payload), encoding="utf-8")
    _seed_customer_and_job(db_path)

    exit_code = main(
        [
            "records",
            "proposal-input",
            "customer-abby-hill",
            "job-abby-hill",
            str(details_path),
            str(output_path),
            "--db",
            str(db_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error: failed to compose proposal input:" in captured.err
    assert "Invalid record proposal details" in captured.err
    assert not output_path.exists()
