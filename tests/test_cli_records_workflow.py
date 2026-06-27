"""Smoke tests for the records CLI workflow."""

from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.records import customer_records_from_json, job_records_from_json

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"


def test_records_cli_import_list_show_export_workflow(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "records.sqlite"
    export_dir = tmp_path / "exports"
    customers_output = export_dir / "customers.json"
    jobs_output = export_dir / "jobs.json"

    assert main(
        [
            "records",
            "import",
            "customer",
            str(CUSTOMER_EXAMPLE),
            "--db",
            str(db_path),
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        ["records", "import", "job", str(JOB_EXAMPLE), "--db", str(db_path)]
    ) == 0
    capsys.readouterr()

    assert main(["records", "list", "customers", "--db", str(db_path)]) == 0
    captured = capsys.readouterr()
    assert "customer-abby-hill" in captured.out

    assert main(["records", "list", "jobs", "--db", str(db_path)]) == 0
    captured = capsys.readouterr()
    assert "job-abby-hill" in captured.out

    assert main(
        [
            "records",
            "show",
            "customer",
            "customer-abby-hill",
            "--db",
            str(db_path),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert "Abby Hill" in captured.out

    assert main(
        ["records", "show", "job", "job-abby-hill", "--db", str(db_path)]
    ) == 0
    captured = capsys.readouterr()
    assert "Abby Hill tank removal proposal" in captured.out
    assert "draft" in captured.out

    assert main(
        [
            "records",
            "export",
            "customers",
            str(customers_output),
            "--db",
            str(db_path),
        ]
    ) == 0
    capsys.readouterr()
    assert customers_output.exists()

    assert main(
        ["records", "export", "jobs", str(jobs_output), "--db", str(db_path)]
    ) == 0
    capsys.readouterr()
    assert jobs_output.exists()

    customers = customer_records_from_json(customers_output.read_text(encoding="utf-8"))
    jobs = job_records_from_json(jobs_output.read_text(encoding="utf-8"))

    assert [customer.customer_id for customer in customers] == ["customer-abby-hill"]
    assert [job.job_id for job in jobs] == ["job-abby-hill"]
