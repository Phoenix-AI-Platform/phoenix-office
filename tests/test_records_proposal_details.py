"""Tests for record proposal details helpers."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ScopeItem
from phoenix_office.records import (
    RecordProposalDetails,
    record_proposal_details_from_dict,
    record_proposal_details_from_file,
    record_proposal_details_from_json,
    record_proposal_details_to_dict,
    record_proposal_details_to_file,
    record_proposal_details_to_json,
)

ROOT = Path(__file__).parents[1]
DETAILS_EXAMPLE = ROOT / "examples" / "records" / "proposal_details_abby_hill.json"


def _details() -> RecordProposalDetails:
    return RecordProposalDetails(
        proposal_date=date(2026, 6, 26),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_items=[
            ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
            ScopeItem(number=2, description="Open and clean tank"),
        ],
        pricing=PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note="Price may change if contents are discovered.",
        ),
        notes=["Customer requested proposal by email."],
        company_config=CompanyConfig(
            company_name="A-1 Tank Removal LLC",
            starting_at_label="Starting at",
            total_label="TOTAL",
        ),
    )


def test_record_proposal_details_preserves_fields() -> None:
    details = _details()

    assert details.proposal_date == date(2026, 6, 26)
    assert details.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert len(details.scope_items) == 2
    assert details.pricing.amount == Decimal("3000.00")
    assert details.notes == ["Customer requested proposal by email."]
    assert details.company_config.company_name == "A-1 Tank Removal LLC"


def test_record_proposal_details_from_dict_and_json() -> None:
    payload = record_proposal_details_to_dict(_details())

    from_dict = record_proposal_details_from_dict(payload)
    from_json = record_proposal_details_from_json(record_proposal_details_to_json(_details()))

    assert from_dict == _details()
    assert from_json == _details()


def test_record_proposal_details_to_dict_uses_json_values() -> None:
    payload = record_proposal_details_to_dict(_details())

    assert payload["proposal_date"] == "2026-06-26"
    assert payload["pricing"]["amount"] == "3000.00"
    assert payload["scope_items"][0]["number"] == 1


def test_record_proposal_details_to_json_is_deterministic() -> None:
    value = record_proposal_details_to_json(_details())

    assert value.endswith("\n")
    assert value == record_proposal_details_to_json(_details())
    assert value.index('"company_config"') < value.index('"item_description"')


def test_record_proposal_details_file_helpers_create_parent_directories(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "proposal_details.json"

    written_path = record_proposal_details_to_file(_details(), output_path)
    loaded = record_proposal_details_from_file(output_path)

    assert written_path == output_path
    assert loaded == _details()


def test_record_proposal_details_example_loads_successfully() -> None:
    details = record_proposal_details_from_file(DETAILS_EXAMPLE)

    assert details.proposal_date == date(2026, 6, 26)
    assert details.item_description == "Removal of 1,000 Gallon Aboveground Storage Tank"
    assert details.pricing.is_starting_at is True
    assert details.notes == []


def test_record_proposal_details_invalid_json_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid record proposal details JSON"):
        record_proposal_details_from_json("{not valid json")


def test_record_proposal_details_non_object_json_raises_value_error() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        record_proposal_details_from_json("[]")


def test_record_proposal_details_invalid_data_raises_value_error() -> None:
    payload = record_proposal_details_to_dict(_details())
    payload["scope_items"] = []

    with pytest.raises(ValueError, match="Invalid record proposal details"):
        record_proposal_details_from_dict(payload)


def test_record_proposal_details_helpers_are_exported_from_records_package() -> None:
    assert callable(record_proposal_details_from_dict)
    assert callable(record_proposal_details_from_file)
    assert callable(record_proposal_details_from_json)
    assert callable(record_proposal_details_to_dict)
    assert callable(record_proposal_details_to_file)
    assert callable(record_proposal_details_to_json)
