"""Tests for the initial-claim store contract boundary."""

from __future__ import annotations

import inspect
import json
from typing import get_type_hints

import pytest

from phoenix_office.core import (
    CodexPilotInitialClaimStore,
    validate_codex_pilot_initial_claim_store_create_result,
)

ALLOWED_CREATE_CATEGORIES = [
    ("created", True),
    ("bundle_invalid", False),
    ("authorization_context_invalid", False),
    ("bundle_binding_mismatch", False),
    ("attempt_id_conflict", False),
    ("authorization_id_conflict", False),
    ("authorization_fingerprint_conflict", False),
    ("claim_store_unavailable", False),
    ("claim_durability_uncertain", False),
    ("commit_incomplete", False),
    ("claim_record_corrupt", False),
    ("audit_event_corrupt", False),
    ("snapshot_corrupt", False),
]


class _DictSubclass(dict):
    pass


class _StrSubclass(str):
    pass


class _Bomb:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(name)

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected dependency access")


def test_codex_pilot_initial_claim_store_protocol_is_exact_and_not_runtime_checkable():
    assert getattr(CodexPilotInitialClaimStore, "_is_runtime_protocol", False) is False

    signature = inspect.signature(CodexPilotInitialClaimStore.create_initial_claim_commit)
    assert list(signature.parameters) == [
        "self",
        "preparation_result",
        "authorization_package",
    ]
    assert signature.return_annotation in ("object", object)

    hints = get_type_hints(CodexPilotInitialClaimStore.create_initial_claim_commit)
    assert hints == {
        "preparation_result": object,
        "authorization_package": object,
        "return": object,
    }


@pytest.mark.parametrize("category, claim_created", ALLOWED_CREATE_CATEGORIES)
def test_validate_codex_pilot_initial_claim_store_create_result_accepts_every_category(
    category: str,
    claim_created: bool,
):
    result = {"claim_store_create_category": category}
    original = dict(result)

    validated = validate_codex_pilot_initial_claim_store_create_result(result)

    assert validated == {
        "claim_store_create_result_valid": True,
        "claim_created": claim_created,
        "claim_store_create_category": category,
        "claim_store_create_result_blockers": [],
    }
    assert result == original


@pytest.mark.parametrize(
    "result, blockers",
    [
        (None, ["claim_store_create_result_invalid"]),
        ([], ["claim_store_create_result_invalid"]),
        ({}, ["claim_store_create_result_invalid", "claim_store_create_category_invalid"]),
        (
            {"claim_store_create_category": "created", "extra": "metadata"},
            ["claim_store_create_result_invalid"],
        ),
        (
            {"claim_store_create_category": " created"},
            ["claim_store_create_category_invalid"],
        ),
        (
            {"claim_store_create_category": "created "},
            ["claim_store_create_category_invalid"],
        ),
        (
            {"claim_store_create_category": "CREATED"},
            ["claim_store_create_category_invalid"],
        ),
        (
            {"claim_store_create_category": "not-a-category"},
            ["claim_store_create_category_invalid"],
        ),
        (
            {"claim_store_create_category": _StrSubclass("created")},
            ["claim_store_create_category_invalid"],
        ),
        (
            _DictSubclass(claim_store_create_category="created"),
            ["claim_store_create_result_invalid"],
        ),
        (
            {"claim_store_create_category": {"nested": True}},
            ["claim_store_create_category_invalid"],
        ),
    ],
)
def test_validate_codex_pilot_initial_claim_store_create_result_rejects_invalid_shapes(
    result: object,
    blockers: list[str],
):
    original = json.loads(json.dumps(result)) if isinstance(result, dict) else result
    validated = validate_codex_pilot_initial_claim_store_create_result(result)

    assert validated["claim_store_create_result_valid"] is False
    assert validated["claim_created"] is None
    assert validated["claim_store_create_category"] is None
    assert validated["claim_store_create_result_blockers"] == sorted(set(blockers))
    if isinstance(result, dict):
        assert result == original


def test_validate_codex_pilot_initial_claim_store_create_result_is_deterministic_and_sanitized():
    result = {"claim_store_create_category": "claim_store_unavailable "}

    first = validate_codex_pilot_initial_claim_store_create_result(result)
    second = validate_codex_pilot_initial_claim_store_create_result(dict(result))
    output = json.dumps(first, sort_keys=True)

    assert first == second
    assert first == {
        "claim_store_create_result_valid": False,
        "claim_created": None,
        "claim_store_create_category": None,
        "claim_store_create_result_blockers": ["claim_store_create_category_invalid"],
    }
    assert "claim_store_unavailable" not in output
    assert "claim_store_unavailable " not in output


def test_validate_initial_claim_store_create_result_no_external_dependencies(monkeypatch):
    import builtins

    import phoenix_office.core.contracts as contracts

    bomb = _Bomb()
    monkeypatch.setattr(contracts, "datetime", bomb, raising=False)
    monkeypatch.setattr(contracts, "Path", bomb, raising=False)
    monkeypatch.setattr(contracts, "random", bomb, raising=False)
    monkeypatch.setattr(contracts, "subprocess", bomb, raising=False)
    monkeypatch.setattr(contracts, "socket", bomb, raising=False)
    monkeypatch.setattr(builtins, "open", bomb, raising=True)

    result = validate_codex_pilot_initial_claim_store_create_result(
        {"claim_store_create_category": "created"}
    )

    assert result == {
        "claim_store_create_result_valid": True,
        "claim_created": True,
        "claim_store_create_category": "created",
        "claim_store_create_result_blockers": [],
    }
