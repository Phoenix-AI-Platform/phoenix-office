"""Canonical byte checks for committed records."""

from __future__ import annotations

import json


def is_canonical_object_bytes(value: object) -> bool:
    if type(value) is not bytes:
        return False
    try:
        parsed = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if type(parsed) is not dict:
        return False
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
    return value == canonical
