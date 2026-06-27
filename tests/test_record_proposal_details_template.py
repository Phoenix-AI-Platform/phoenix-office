"""Tests for the RecordProposalDetails starter template."""

from pathlib import Path

from phoenix_office.records import (
    RecordProposalDetails,
    record_proposal_details_from_file,
)

ROOT = Path(__file__).parents[1]
DETAILS_TEMPLATE = ROOT / "examples" / "records" / "proposal_details_template.json"


def test_record_proposal_details_template_loads_successfully() -> None:
    details = record_proposal_details_from_file(DETAILS_TEMPLATE)

    assert isinstance(details, RecordProposalDetails)
    assert "Describe the tank removal work here" in details.item_description
    assert "Add scope item here" in details.scope_items[0].description
    assert details.notes == ["Add proposal note here"]
