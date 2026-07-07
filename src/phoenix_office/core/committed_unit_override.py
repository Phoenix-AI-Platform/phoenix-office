"""Fail-closed committed-unit validation wrapper."""

from __future__ import annotations

import phoenix_office.core.contracts as _contracts
from phoenix_office.core.committed_bytes_guard import is_canonical_object_bytes
from phoenix_office.core.committed_value_guard import is_exact_json_value

_RECORDS = {
    "claim_record": ("claim_record_corrupt", "claim_record_bytes"),
    "sequence_zero_event": ("audit_event_corrupt", "sequence_zero_event_bytes"),
    "snapshot": ("snapshot_corrupt", "snapshot_bytes"),
}


def validate_codex_pilot_initial_claim_committed_unit(
    committed_unit: object,
    attempt_id: object,
    authorization_package: object,
) -> dict[str, object]:
    if type(committed_unit) is not dict:
        return _contracts.validate_codex_pilot_initial_claim_committed_unit(
            committed_unit, attempt_id, authorization_package
        )

    candidate = dict(committed_unit)
    forced: set[str] = set()
    for field_name, (blocker, bytes_field) in _RECORDS.items():
        record = committed_unit.get(field_name)
        if type(record) is dict and not is_exact_json_value(record):
            candidate[field_name] = {}
            if is_canonical_object_bytes(committed_unit.get(bytes_field)):
                candidate[bytes_field] = b"{}"
            forced.add(blocker)

    result = _contracts.validate_codex_pilot_initial_claim_committed_unit(
        candidate, attempt_id, authorization_package
    )
    if not forced:
        return result

    blockers = set(result["committed_unit_blockers"])
    blockers.update(forced)
    return {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": sorted(blockers),
    }
