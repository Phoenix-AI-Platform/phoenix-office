"""Tests for the initial-claim store contract boundary."""

from __future__ import annotations

import inspect
import json
from enum import Enum, StrEnum
from typing import get_type_hints

import pytest

from phoenix_office.core import (
    CodexPilotInitialClaimReader,
    CodexPilotInitialClaimStore,
    validate_codex_pilot_initial_claim_store_create_result,
    validate_codex_pilot_initial_claim_store_read_result,
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

ALLOWED_READ_CATEGORIES = [
    ("read_success", True),
    ("attempt_id_invalid", False),
    ("authorization_context_invalid", False),
    ("bundle_binding_mismatch", False),
    ("missing_commit", False),
    ("commit_incomplete", False),
    ("claim_record_corrupt", False),
    ("audit_event_corrupt", False),
    ("snapshot_corrupt", False),
    ("uniqueness_entry_corrupt", False),
    ("digest_mismatch", False),
    ("identity_mismatch", False),
    ("history_mismatch", False),
    ("claim_store_unavailable", False),
    ("claim_durability_uncertain", False),
]


class _DictSubclass(dict):
    pass


class _StrSubclass(str):
    pass


class _FieldEnum(Enum):
    CLAIM_STORE_CREATE_CATEGORY = "claim_store_create_category"


class _FieldStrEnum(StrEnum):
    CLAIM_STORE_CREATE_CATEGORY = "claim_store_create_category"


class _TruthyCategory:
    def __bool__(self) -> bool:
        return True


class _HostileKey:
    def __hash__(self) -> int:
        return 0

    def __eq__(self, other: object) -> bool:
        raise AssertionError("unexpected equality check")


class _Bomb:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(name)

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected dependency access")


def test_codex_pilot_initial_claim_store_protocol_is_exact_and_not_runtime_checkable():
    assert getattr(CodexPilotInitialClaimStore, "_is_runtime_protocol", False) is False
    with pytest.raises(TypeError):
        isinstance(object(), CodexPilotInitialClaimStore)

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
    "result",
    [
        None,
        [],
        {},
        {"claim_store_create_category": "created", "extra": "metadata"},
        _DictSubclass(claim_store_create_category="created"),
        {_StrSubclass("claim_store_create_category"): "created"},
        {_FieldEnum.CLAIM_STORE_CREATE_CATEGORY: "created"},
        {_FieldStrEnum.CLAIM_STORE_CREATE_CATEGORY: "created"},
        {_HostileKey(): "created"},
    ],
)
def test_validate_codex_pilot_initial_claim_store_create_result_rejects_invalid_field_shapes(
    result: object,
):
    original = dict(result) if isinstance(result, dict) else result
    validated = validate_codex_pilot_initial_claim_store_create_result(result)

    assert validated == {
        "claim_store_create_result_valid": False,
        "claim_created": None,
        "claim_store_create_category": None,
        "claim_store_create_result_blockers": ["claim_store_create_result_invalid"],
    }
    if isinstance(result, dict):
        assert result == original


@pytest.mark.parametrize(
    "category",
    [
        None,
        False,
        True,
        0,
        1,
        "not-a-category",
        " created",
        "CREATED",
        {"nested": True},
        _FieldEnum.CLAIM_STORE_CREATE_CATEGORY,
        _FieldStrEnum.CLAIM_STORE_CREATE_CATEGORY,
        Exception("created"),
        _TruthyCategory(),
        _StrSubclass("created"),
    ],
)
def test_validate_codex_pilot_initial_claim_store_create_result_rejects_invalid_category_types(
    category: object,
):
    result = {"claim_store_create_category": category}
    original = dict(result)

    validated = validate_codex_pilot_initial_claim_store_create_result(result)

    assert validated == {
        "claim_store_create_result_valid": False,
        "claim_created": None,
        "claim_store_create_category": None,
        "claim_store_create_result_blockers": ["claim_store_create_category_invalid"],
    }
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


def test_codex_pilot_initial_claim_reader_protocol_is_exact_and_not_runtime_checkable():
    assert getattr(CodexPilotInitialClaimReader, "_is_runtime_protocol", False) is False
    with pytest.raises(TypeError):
        isinstance(object(), CodexPilotInitialClaimReader)

    signature = inspect.signature(CodexPilotInitialClaimReader.read_initial_claim_bundle)
    assert list(signature.parameters) == [
        "self",
        "attempt_id",
        "authorization_package",
    ]
    assert signature.return_annotation in ("object", object)

    hints = get_type_hints(CodexPilotInitialClaimReader.read_initial_claim_bundle)
    assert hints == {
        "attempt_id": object,
        "authorization_package": object,
        "return": object,
    }


@pytest.mark.parametrize("category, claim_read_succeeded", ALLOWED_READ_CATEGORIES)
def test_validate_codex_pilot_initial_claim_store_read_result_accepts_every_category(
    category: str,
    claim_read_succeeded: bool,
):
    result = {"claim_store_read_category": category}
    original = dict(result)

    validated = validate_codex_pilot_initial_claim_store_read_result(result)

    assert validated == {
        "claim_store_read_result_valid": True,
        "claim_read_succeeded": claim_read_succeeded,
        "claim_store_read_category": category,
        "claim_store_read_result_blockers": [],
    }
    assert result == original


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {},
        {"claim_store_read_category": "read_success", "extra": "metadata"},
        {"claim_store_create_category": "read_success"},
        _DictSubclass(claim_store_read_category="read_success"),
        {_StrSubclass("claim_store_read_category"): "read_success"},
        {_FieldEnum.CLAIM_STORE_CREATE_CATEGORY: "read_success"},
        {_FieldStrEnum.CLAIM_STORE_CREATE_CATEGORY: "read_success"},
        {_HostileKey(): "read_success"},
    ],
)
def test_validate_codex_pilot_initial_claim_store_read_result_rejects_invalid_field_shapes(
    result: object,
):
    original = dict(result) if isinstance(result, dict) else result
    validated = validate_codex_pilot_initial_claim_store_read_result(result)

    assert validated == {
        "claim_store_read_result_valid": False,
        "claim_read_succeeded": None,
        "claim_store_read_category": None,
        "claim_store_read_result_blockers": ["claim_store_read_result_invalid"],
    }
    if isinstance(result, dict):
        assert result == original


@pytest.mark.parametrize(
    "category",
    [
        None,
        False,
        True,
        0,
        1,
        "not-a-category",
        " read_success",
        "READ_SUCCESS",
        {"nested": True},
        _FieldEnum.CLAIM_STORE_CREATE_CATEGORY,
        _FieldStrEnum.CLAIM_STORE_CREATE_CATEGORY,
        Exception("read_success"),
        _TruthyCategory(),
        _StrSubclass("read_success"),
    ],
)
def test_validate_codex_pilot_initial_claim_store_read_result_rejects_invalid_category_types(
    category: object,
):
    result = {"claim_store_read_category": category}
    original = dict(result)

    validated = validate_codex_pilot_initial_claim_store_read_result(result)

    assert validated == {
        "claim_store_read_result_valid": False,
        "claim_read_succeeded": None,
        "claim_store_read_category": None,
        "claim_store_read_result_blockers": ["claim_store_read_category_invalid"],
    }
    assert result == original


def test_validate_codex_pilot_initial_claim_store_read_result_is_deterministic_and_sanitized():
    result = {"claim_store_read_category": "claim_store_unavailable "}

    first = validate_codex_pilot_initial_claim_store_read_result(result)
    second = validate_codex_pilot_initial_claim_store_read_result(dict(result))
    output = json.dumps(first, sort_keys=True)

    assert first == second
    assert first == {
        "claim_store_read_result_valid": False,
        "claim_read_succeeded": None,
        "claim_store_read_category": None,
        "claim_store_read_result_blockers": ["claim_store_read_category_invalid"],
    }
    assert "claim_store_unavailable" not in output
    assert "claim_store_unavailable " not in output


def test_validate_codex_pilot_initial_claim_store_read_result_no_external_dependencies(
    monkeypatch,
):
    import builtins

    import phoenix_office.core.contracts as contracts

    bomb = _Bomb()
    monkeypatch.setattr(contracts, "datetime", bomb, raising=False)
    monkeypatch.setattr(contracts, "Path", bomb, raising=False)
    monkeypatch.setattr(contracts, "random", bomb, raising=False)
    monkeypatch.setattr(contracts, "subprocess", bomb, raising=False)
    monkeypatch.setattr(contracts, "socket", bomb, raising=False)
    monkeypatch.setattr(builtins, "open", bomb, raising=True)

    result = validate_codex_pilot_initial_claim_store_read_result(
        {"claim_store_read_category": "read_success"}
    )

    assert result == {
        "claim_store_read_result_valid": True,
        "claim_read_succeeded": True,
        "claim_store_read_category": "read_success",
        "claim_store_read_result_blockers": [],
    }


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
