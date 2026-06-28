"""Smoke test for the record-backed proposal CLI workflow."""

import json
from decimal import Decimal
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_abby_hill.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_abby_hill.json"
DETAILS_EXAMPLE = ROOT / "examples" / "records" / "proposal_details_abby_hill.json"
TEMPLATE = ROOT / "tests" / "fixtures" / "templates" / "a1_proposal_template.docx"


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_records_cli_proposal_input_to_docx_workflow(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    proposal_input_path = tmp_path / "proposal" / "abby_hill_proposal_input.json"
    output_docx_path = tmp_path / "proposal" / "abby_hill_proposal.docx"

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

    assert main(
        [
            "records",
            "proposal-details",
            "validate",
            str(DETAILS_EXAMPLE),
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "records",
            "proposal-input",
            "customer-abby-hill",
            "job-abby-hill",
            str(DETAILS_EXAMPLE),
            str(proposal_input_path),
            "--db",
            str(db_path),
        ]
    ) == 0
    capsys.readouterr()

    assert proposal_input_path.exists()
    proposal = ProposalInput.model_validate(
        json.loads(proposal_input_path.read_text(encoding="utf-8"))
    )
    assert proposal.customer_name == "Abby Hill"
    assert (
        proposal.item_description
        == "Removal of 1,000 Gallon Aboveground Storage Tank"
    )
    assert proposal.street_address == "123 Main St."
    assert proposal.city_state_zip == "Menomonee Falls, WI 53051"
    assert len(proposal.scope_items) == 4
    assert [item.description for item in proposal.scope_items] == [
        "Pump contents of tank (contents unknown)",
        "Open and clean tank",
        "Remove 1,000 gallon AST",
        "Remove and dispose of tank and residual contents",
    ]
    assert proposal.pricing.amount == Decimal("3000.00")
    assert proposal.pricing.is_starting_at is True
    assert proposal.notes == []

    assert main(["proposal", "validate", str(proposal_input_path)]) == 0
    capsys.readouterr()

    assert main(["proposal", "inspect", str(proposal_input_path)]) == 0
    captured = capsys.readouterr()
    inspect_output = _collapse_whitespace(captured.out)
    assert "Customer: Abby Hill" in inspect_output
    assert "Site Address: 123 Main St., Menomonee Falls, WI 53051" in inspect_output
    assert "Item Description: Removal of 1,000 Gallon Aboveground Storage Tank" in inspect_output
    assert "Scope Items: 4" in inspect_output
    assert "Total: Starting at $3,000.00" in inspect_output
    assert "Notes: none" in inspect_output

    assert main(
        [
            "proposal",
            "generate",
            str(proposal_input_path),
            str(output_docx_path),
            "--template",
            str(TEMPLATE),
        ]
    ) == 0
    capsys.readouterr()

    assert output_docx_path.exists()
    assert output_docx_path.stat().st_size > 0
