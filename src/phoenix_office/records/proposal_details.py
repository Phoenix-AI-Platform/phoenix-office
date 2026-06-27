"""Explicit proposal details for record-backed proposal input."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ScopeItem


class RecordProposalDetails(BaseModel):
    """Non-record proposal details used with customer and job records.

    Customer and site fields intentionally live on CustomerRecord and JobRecord.
    This model holds only explicit proposal details that should not be inferred
    from records.
    """

    proposal_date: date = Field(..., description="Date printed on the proposal.")
    item_description: str = Field(
        ...,
        min_length=1,
        description="Short description of the primary work item.",
    )
    scope_items: list[ScopeItem] = Field(
        ...,
        min_length=1,
        description="Explicit ordered scope-of-work items.",
    )
    pricing: PricingLine = Field(..., description="Explicit proposal pricing.")
    notes: list[str] = Field(default_factory=list)
    company_config: CompanyConfig = Field(default_factory=CompanyConfig)


def record_proposal_details_from_dict(value: dict[str, Any]) -> RecordProposalDetails:
    """Parse proposal details from a dictionary."""
    try:
        return RecordProposalDetails.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"Invalid record proposal details: {exc}") from exc


def record_proposal_details_to_dict(details: RecordProposalDetails) -> dict[str, Any]:
    """Serialize proposal details to a JSON-compatible dictionary."""
    return details.model_dump(mode="json")


def record_proposal_details_from_json(value: str) -> RecordProposalDetails:
    """Parse proposal details from a JSON object string."""
    try:
        data: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid record proposal details JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError("Record proposal details JSON must be an object.")

    return record_proposal_details_from_dict(data)


def record_proposal_details_to_json(details: RecordProposalDetails) -> str:
    """Serialize proposal details to deterministic, human-readable JSON."""
    payload = record_proposal_details_to_dict(details)
    return f"{json.dumps(payload, indent=2, sort_keys=True)}\n"


def record_proposal_details_from_file(path: Path) -> RecordProposalDetails:
    """Read proposal details from a UTF-8 JSON file."""
    return record_proposal_details_from_json(path.read_text(encoding="utf-8"))


def record_proposal_details_to_file(details: RecordProposalDetails, path: Path) -> Path:
    """Write proposal details to a UTF-8 JSON file and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record_proposal_details_to_json(details), encoding="utf-8")
    return path
