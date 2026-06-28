"""Smoke test for a second sanitized record-backed proposal workflow."""

import json
from decimal import Decimal
from pathlib import Path

from phoenix_office.cli import main
from phoenix_office.models.proposal import ProposalInput

ROOT = Path(__file__).parents[1]
CUSTOMER_EXAMPLE = ROOT / "examples" / "records" / "customer_sample_north_prairie.json"
JOB_EXAMPLE = ROOT / "examples" / "records" / "job_sample_north_prairie.json"
DETAILS_EXAMPLE = ROOT / "examples" / "records" / "proposal_details_sample_north_prairie.json"
TEMPLATE = ROOT / "tests" / "fixtures" / "templates" / "a1_proposal_template.docx"


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_sample_north_prairie_records_to_docx_workflow(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "records.sqlite"
    proposal_input_path = tmp_path / "proposal" / "sample_north_prairie_input.json"
    output_docx_path = tmp_path / "proposal" / "sample_north_prairie.docx"

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
            "customer-sample-north-prairie",
            "job-sample-north-prairie",
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
    assert proposal.customer_name == "Sample North Prairie Customer"
    assert proposal.item_description == "Removal of two 550 Gallon Aboveground Storage Tanks"
    assert proposal.street_address == "100 Sample Site Rd."
    assert proposal.city_state_zip == "North Prairie, WI 53153"
    assert len(proposal.scope_items) == 4
    assert [item.description for item in proposal.scope_items] == [
        "Remove two 550 gallon aboveground storage tanks.",
        "Pump and clean remaining accessible tank contents as required for removal.",
        "Disconnect and remove associated accessible tank piping.",
        "Haul tanks and related debris from site.",
    ]
    assert proposal.pricing.amount == Decimal("5400.00")
    assert proposal.pricing.is_starting_at is False
    assert proposal.notes == [
        "Proposal is based on accessible aboveground tanks and operator-authored scope."
    ]

    assert main(["proposal", "validate", str(proposal_input_path)]) == 0
    capsys.readouterr()

    assert main(["proposal", "inspect", str(proposal_input_path)]) == 0
    captured = capsys.readouterr()
    inspect_output = _collapse_whitespace(captured.out)
    assert "Customer: Sample North Prairie Customer" in inspect_output
    assert "Site Address: 100 Sample Site Rd., North Prairie, WI 53153" in inspect_output
    assert (
        "Item Description: Removal of two 550 Gallon Aboveground Storage Tanks"
        in inspect_output
    )
    assert "Scope Items: 4" in inspect_output
    assert "Total: $5,400.00" in inspect_output
    assert "Notes: present" in inspect_output

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
