"""Tests for the initial-claim store contract boundary."""

from __future__ import annotations

import copy
import inspect
import json
from enum import Enum, StrEnum
from typing import get_type_hints

import pytest

from phoenix_office.core import (
    CodexPilotInitialClaimReader,
    CodexPilotInitialClaimStore,
    codex_pilot_audit_event_digest,
    compose_codex_pilot_initial_claim_bundle,
    prepare_codex_pilot_initial_claim_commit,
    validate_codex_pilot_initial_claim_committed_unit,
    validate_codex_pilot_initial_claim_read_request,
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


class _HostileCommittedUnit:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(name)


def _valid_codex_pilot_authorization_packet() -> dict[str, object]:
    return {
        "schema_version": "codex-pilot-authorization.v1",
        "authorization_id": "pilot-auth-issue-320",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "decision_state": "human_authorized_for_one_run",
        "authorizer_role": "human_operator",
        "base_commit_sha": "0" * 40,
        "handoff_path": "docs/process/supervised-codex-pilot-handoff.json",
        "evidence_path": "docs/process/supervised-codex-pilot-evidence.json",
        "handoff_id": "codex-handoff-issue-320",
        "objective": "Document the supervised Codex pilot authorization packet.",
        "allowed_paths": ["docs/process/supervised-codex-pilot-storage.md"],
        "expected_pr_title": "docs: update supervised Codex pilot authorization",
        "branch_name": "codex/supervised-pilot-authorization",
        "validation_commands": [
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
            "python -m ruff check . --no-cache",
            "git diff --check",
        ],
        "budget_metric": "tokens",
        "budget_ceiling": 50000,
        "budget_enforcement_ref": "budget-control-reviewed",
        "timeout_seconds": 3600,
        "cancellation_ref": "cancellation-control-reviewed",
        "authentication_runner_ref": "authentication-runner-reviewed",
        "branch_permission_ref": "branch-permission-reviewed",
        "pr_permission_ref": "pr-permission-reviewed",
        "duplicate_pr_check_ref": "duplicate-pr-check-reviewed",
        "branch_collision_check_ref": "branch-collision-check-reviewed",
        "codex_no_approve_merge_ref": "codex-no-approve-merge-reviewed",
        "final_ci_required": True,
        "assistant_review_required": True,
        "worker_may_approve": False,
        "worker_may_merge": False,
        "one_invocation_only": True,
        "retry_authorized": False,
        "background_execution_authorized": False,
    }


def _canonical_json_bytes(record: object) -> bytes:
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _valid_codex_pilot_committed_unit() -> tuple[dict[str, object], dict[str, object]]:
    authorization = _valid_codex_pilot_authorization_packet()
    bundle = compose_codex_pilot_initial_claim_bundle(authorization, VALID_ATTEMPT_ID)
    assert bundle["claim_bundle_passed"] is True
    preparation = prepare_codex_pilot_initial_claim_commit(bundle, authorization)
    committed_unit = preparation["prepared_commit"]
    assert committed_unit is not None
    return committed_unit, authorization


VALID_ATTEMPT_ID = "pilot-attempt-abc123def456"
VALID_ATTEMPT_ID_NON_HEX = "pilot-attempt-abc123defghz"


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


def test_validate_codex_pilot_initial_claim_read_request_is_valid_deterministic_and_pure():
    authorization = _valid_codex_pilot_authorization_packet()
    original = copy.deepcopy(authorization)

    first = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID,
        authorization,
    )
    second = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID,
        copy.deepcopy(authorization),
    )

    assert first == second
    assert first == {
        "claim_read_request_valid": True,
        "attempt_id_valid": True,
        "authorization_context_valid": True,
        "claim_read_request_blockers": [],
    }
    assert authorization == original


def test_validate_codex_pilot_initial_claim_read_request_accepts_safe_non_hex_letters():
    authorization = _valid_codex_pilot_authorization_packet()
    original = copy.deepcopy(authorization)

    result = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID_NON_HEX,
        authorization,
    )

    assert result == {
        "claim_read_request_valid": True,
        "attempt_id_valid": True,
        "authorization_context_valid": True,
        "claim_read_request_blockers": [],
    }
    assert authorization == original


@pytest.mark.parametrize(
    "attempt_id",
    [
        _StrSubclass(VALID_ATTEMPT_ID),
        f" {VALID_ATTEMPT_ID}",
        f"{VALID_ATTEMPT_ID} ",
        "PILOT-ATTEMPT-ABC123DEF456",
        "pilot-attemptabc123def456",
        "pilot-attempt-abc123def45",
        "pilot-attempt-abc123def456789012345678901234567890123456789012345678901234567890123",
        "pilot-attempt-abc123defhome456",
        True,
        1,
        b"pilot-attempt-abc123def456",
        _FieldEnum.CLAIM_STORE_CREATE_CATEGORY,
        {"attempt_id": VALID_ATTEMPT_ID},
        Exception("pilot-attempt-abc123def456"),
        _TruthyCategory(),
    ],
)
def test_validate_codex_pilot_initial_claim_read_request_rejects_invalid_attempt_ids(
    attempt_id: object,
):
    authorization = _valid_codex_pilot_authorization_packet()
    original = copy.deepcopy(authorization)

    result = validate_codex_pilot_initial_claim_read_request(attempt_id, authorization)
    output = json.dumps(result, sort_keys=True)

    assert result == {
        "claim_read_request_valid": False,
        "attempt_id_valid": False,
        "authorization_context_valid": True,
        "claim_read_request_blockers": ["attempt_id_invalid"],
    }
    if isinstance(attempt_id, str):
        assert attempt_id not in output
    assert authorization == original


@pytest.mark.parametrize(
    "authorization_package",
    [
        None,
        [],
        {"schema_version": "codex-pilot-authorization.v1"},
        {
            **_valid_codex_pilot_authorization_packet(),
            "objective": {"nested": True},
        },
        {
            **_valid_codex_pilot_authorization_packet(),
            "allowed_paths": [
                "docs/process/zeta.md",
                "docs/process/alpha.md",
            ],
        },
    ],
)
def test_validate_codex_pilot_initial_claim_read_request_rejects_invalid_authorization_contexts(
    authorization_package: object,
):
    original = copy.deepcopy(authorization_package)

    result = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID,
        authorization_package,
    )

    assert result == {
        "claim_read_request_valid": False,
        "attempt_id_valid": True,
        "authorization_context_valid": False,
        "claim_read_request_blockers": ["authorization_context_invalid"],
    }
    if isinstance(authorization_package, dict):
        assert authorization_package == original


def test_validate_codex_pilot_initial_claim_read_request_authorization_no_echo():
    sentinel = "sentinel-authorization-objective-987654321"
    authorization_package = {
        **_valid_codex_pilot_authorization_packet(),
        "objective": {"nested": sentinel},
    }
    original = copy.deepcopy(authorization_package)

    result = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID,
        authorization_package,
    )
    output = json.dumps(result, sort_keys=True)

    assert result == {
        "claim_read_request_valid": False,
        "attempt_id_valid": True,
        "authorization_context_valid": False,
        "claim_read_request_blockers": ["authorization_context_invalid"],
    }
    assert authorization_package == original
    assert sentinel not in output
    assert sentinel not in "".join(result["claim_read_request_blockers"])


def test_validate_codex_pilot_initial_claim_read_request_no_external_dependencies(monkeypatch):
    import builtins

    import phoenix_office.core.contracts as contracts

    bomb = _Bomb()
    monkeypatch.setattr(contracts, "datetime", bomb, raising=False)
    monkeypatch.setattr(contracts, "Path", bomb, raising=False)
    monkeypatch.setattr(contracts, "random", bomb, raising=False)
    monkeypatch.setattr(contracts, "subprocess", bomb, raising=False)
    monkeypatch.setattr(contracts, "socket", bomb, raising=False)
    monkeypatch.setattr(builtins, "open", bomb, raising=True)

    result = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID_NON_HEX,
        _valid_codex_pilot_authorization_packet(),
    )

    assert result == {
        "claim_read_request_valid": True,
        "attempt_id_valid": True,
        "authorization_context_valid": True,
        "claim_read_request_blockers": [],
    }


@pytest.mark.parametrize(
    "failing_helper",
    [
        "codex_pilot_authorization_fingerprint",
        "codex_pilot_objective_digest",
    ],
)
def test_validate_codex_pilot_initial_claim_read_request_fails_closed_on_digest_errors(
    monkeypatch,
    failing_helper: str,
):
    import phoenix_office.core.contracts as contracts

    authorization = _valid_codex_pilot_authorization_packet()

    def _raise_value_error(*args: object, **kwargs: object) -> str:
        raise ValueError("boom")

    monkeypatch.setattr(contracts, failing_helper, _raise_value_error)

    result = validate_codex_pilot_initial_claim_read_request(
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "claim_read_request_valid": False,
        "attempt_id_valid": True,
        "authorization_context_valid": False,
        "claim_read_request_blockers": ["authorization_context_invalid"],
    }
    assert authorization == _valid_codex_pilot_authorization_packet()


def test_validate_codex_pilot_initial_claim_read_request_checks_both_inputs(
    monkeypatch,
):
    import phoenix_office.core.contracts as contracts

    calls: list[str] = []

    def _fake_attempt_id(value: object) -> bool:
        calls.append("attempt_id")
        return False

    def _fake_authorization_packet(value: object) -> dict[str, object]:
        calls.append("authorization")
        return {
            "authorization_structural_valid": False,
            "authorization_structural_errors": ["authorization package root must be an object"],
        }

    monkeypatch.setattr(contracts, "_is_exact_codex_pilot_attempt_id", _fake_attempt_id)
    monkeypatch.setattr(
        contracts,
        "validate_codex_pilot_authorization_packet",
        _fake_authorization_packet,
    )

    result = validate_codex_pilot_initial_claim_read_request(
        _StrSubclass(VALID_ATTEMPT_ID),
        object(),
    )

    assert calls == ["attempt_id", "authorization"]
    assert result == {
        "claim_read_request_valid": False,
        "attempt_id_valid": False,
        "authorization_context_valid": False,
        "claim_read_request_blockers": [
            "attempt_id_invalid",
            "authorization_context_invalid",
        ],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_is_valid_deterministic_and_pure():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    original_unit = copy.deepcopy(committed_unit)
    original_authorization = copy.deepcopy(authorization)

    first = validate_codex_pilot_initial_claim_committed_unit(
        committed_unit,
        VALID_ATTEMPT_ID,
        authorization,
    )
    second = validate_codex_pilot_initial_claim_committed_unit(
        copy.deepcopy(committed_unit),
        VALID_ATTEMPT_ID,
        copy.deepcopy(authorization),
    )

    assert first == second
    assert first == {
        "committed_unit_validation_passed": True,
        "committed_unit_blockers": [],
    }
    assert committed_unit == original_unit
    assert authorization == original_authorization


@pytest.mark.parametrize(
    "attempt_id, authorization_package, expected_blockers",
    [
        (
            _StrSubclass("pilot-attempt-abc123def457"),
            _valid_codex_pilot_authorization_packet(),
            ["attempt_id_invalid"],
        ),
        (
            VALID_ATTEMPT_ID,
            object(),
            ["authorization_context_invalid"],
        ),
        (
            _StrSubclass("pilot-attempt-abc123def457"),
            object(),
            ["attempt_id_invalid", "authorization_context_invalid"],
        ),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_invalid_request_without_touching_unit(  # noqa: E501
    attempt_id: object,
    authorization_package: object,
    expected_blockers: list[str],
):
    result = validate_codex_pilot_initial_claim_committed_unit(
        _HostileCommittedUnit(),
        attempt_id,
        authorization_package,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": expected_blockers,
    }


@pytest.mark.parametrize(
    "committed_unit",
    [
        None,
        [],
        _DictSubclass(),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_invalid_roots(
    committed_unit: object,
):
    authorization = _valid_codex_pilot_authorization_packet()
    result = validate_codex_pilot_initial_claim_committed_unit(
        committed_unit,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["commit_incomplete"],
    }


@pytest.mark.parametrize(
    "candidate_kind",
    [
        "missing_field",
        "extra_field",
        "dict_subclass",
        "hostile_keys",
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_invalid_root_fields(
    candidate_kind: str,
):
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    if candidate_kind == "missing_field":
        candidate.pop("snapshot_bytes")
    elif candidate_kind == "extra_field":
        candidate["extra"] = "metadata"
    elif candidate_kind == "dict_subclass":
        candidate = _DictSubclass(candidate)
    else:
        candidate = {_HostileKey(): "metadata"}

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["commit_incomplete"],
    }


@pytest.mark.parametrize(
    "field_name, replacement",
    [
        ("claim_record", None),
        ("sequence_zero_event", []),
        ("snapshot", None),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_corrupt_records(
    field_name: str,
    replacement: object,
):
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate[field_name] = replacement

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    expected_blocker = {
        "claim_record": "claim_record_corrupt",
        "sequence_zero_event": "audit_event_corrupt",
        "snapshot": "snapshot_corrupt",
    }[field_name]
    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": [expected_blocker],
    }


@pytest.mark.parametrize(
    "field_name, bytes_value",
    [
        ("claim_record_bytes", bytearray(b"{}")),
        ("sequence_zero_event_bytes", bytearray(b"{}")),
        ("snapshot_bytes", bytearray(b"{}")),
        ("claim_record_bytes", b"\xff"),
        ("sequence_zero_event_bytes", b"{not-json}"),
        ("snapshot_bytes", b"{not-json}"),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_wrong_type_and_malformed_bytes(
    field_name: str,
    bytes_value: object,
):
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate[field_name] = bytes_value

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["digest_mismatch"],
    }


@pytest.mark.parametrize(
    "field_name, mode",
    [
        ("claim_record_bytes", "stale"),
        ("sequence_zero_event_bytes", "stale"),
        ("snapshot_bytes", "stale"),
        ("claim_record_bytes", "noncanonical"),
        ("sequence_zero_event_bytes", "noncanonical"),
        ("snapshot_bytes", "noncanonical"),
        ("claim_record_bytes", "mismatched"),
        ("sequence_zero_event_bytes", "mismatched"),
        ("snapshot_bytes", "mismatched"),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_stale_noncanonical_and_mismatched_bytes(  # noqa: E501
    field_name: str,
    mode: str,
):
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    record_name = field_name.removesuffix("_bytes")
    record = candidate[record_name]

    if mode == "stale":
        stale_record = copy.deepcopy(record)
        stale_record["_stale_marker"] = True
        candidate[field_name] = _canonical_json_bytes(stale_record)
    elif mode == "noncanonical":
        candidate[field_name] = json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")
    else:
        other_record_name = {
            "claim_record_bytes": "sequence_zero_event",
            "sequence_zero_event_bytes": "snapshot",
            "snapshot_bytes": "claim_record",
        }[field_name]
        candidate[field_name] = _canonical_json_bytes(candidate[other_record_name])

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["digest_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_detects_requested_attempt_id_mismatch():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    result = validate_codex_pilot_initial_claim_committed_unit(
        committed_unit,
        "pilot-attempt-abc123def457",
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["identity_mismatch"],
    }


@pytest.mark.parametrize(
    "field_name, replacement",
    [
        ("attempt_id", VALID_ATTEMPT_ID_NON_HEX),
        ("authorization_id", "pilot-auth-issue-321"),
        ("authorization_fingerprint", "f" * 64),
    ],
)
def test_validate_codex_pilot_initial_claim_committed_unit_rejects_cross_record_identity_mismatches(  # noqa: E501
    field_name: str,
    replacement: str,
):
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate["sequence_zero_event"][field_name] = replacement
    candidate["snapshot"][field_name] = replacement
    candidate["sequence_zero_event"]["event_digest"] = codex_pilot_audit_event_digest(
        {
            key: value
            for key, value in candidate["sequence_zero_event"].items()
            if key != "event_digest"
        }
    )
    candidate["snapshot"]["latest_event_digest"] = candidate["sequence_zero_event"]["event_digest"]
    candidate["sequence_zero_event_bytes"] = _canonical_json_bytes(
        candidate["sequence_zero_event"]
    )
    candidate["snapshot_bytes"] = _canonical_json_bytes(candidate["snapshot"])

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["identity_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_authorization_binding_mismatch():  # noqa: E501
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    authorization = copy.deepcopy(authorization)
    authorization["objective"] = "Document the supervised Codex pilot authorization packet v2."

    result = validate_codex_pilot_initial_claim_committed_unit(
        committed_unit,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["bundle_binding_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_event_digest_mismatch():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    wrong_digest = "f" * 64
    candidate["sequence_zero_event"]["event_digest"] = wrong_digest
    candidate["snapshot"]["latest_event_digest"] = wrong_digest
    candidate["sequence_zero_event_bytes"] = _canonical_json_bytes(
        candidate["sequence_zero_event"]
    )
    candidate["snapshot_bytes"] = _canonical_json_bytes(candidate["snapshot"])

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["digest_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_sequence_zero_history_mismatch():  # noqa: E501
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    event = candidate["sequence_zero_event"]
    event["event_sequence"] = 1
    event["previous_lifecycle_state"] = "claim_created"
    event["next_lifecycle_state"] = "invocation_starting"
    event["event_category"] = "invocation_starting"
    event["result_category"] = "started"
    event["actor_role"] = "phoenix_gate"
    event["previous_event_digest"] = candidate["sequence_zero_event"]["event_digest"]
    event["event_digest"] = codex_pilot_audit_event_digest(
        {key: value for key, value in event.items() if key != "event_digest"}
    )
    candidate["snapshot"]["latest_event_digest"] = event["event_digest"]
    candidate["snapshot_bytes"] = _canonical_json_bytes(candidate["snapshot"])
    candidate["sequence_zero_event_bytes"] = _canonical_json_bytes(event)

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["history_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_snapshot_history_mismatch():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    snapshot = candidate["snapshot"]
    snapshot["latest_event_sequence"] = 1
    snapshot["latest_event_digest"] = candidate["sequence_zero_event"]["event_digest"]
    snapshot["current_lifecycle_state"] = "invocation_starting"
    snapshot["terminal"] = False
    candidate["snapshot_bytes"] = _canonical_json_bytes(snapshot)

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["history_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_uniqueness_structural_failure():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate["uniqueness_entries"] = [candidate["uniqueness_entries"][0]]

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["uniqueness_entry_corrupt"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_rejects_uniqueness_identity_mismatch():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate["uniqueness_entries"][0] = {
        "attempt_id": {"attempt_id": "pilot-attempt-abc123def457"}
    }

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": ["identity_mismatch"],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_is_sorted_deduplicated_and_sanitized():
    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    candidate = copy.deepcopy(committed_unit)
    candidate["sequence_zero_event"]["event_sequence"] = 1
    candidate["sequence_zero_event"]["previous_lifecycle_state"] = "claim_created"
    candidate["sequence_zero_event"]["next_lifecycle_state"] = "invocation_starting"
    candidate["sequence_zero_event"]["event_category"] = "invocation_starting"
    candidate["sequence_zero_event"]["result_category"] = "started"
    candidate["sequence_zero_event"]["actor_role"] = "phoenix_gate"
    candidate["sequence_zero_event"]["previous_event_digest"] = committed_unit[
        "sequence_zero_event"
    ]["event_digest"]
    candidate["sequence_zero_event"]["event_digest"] = codex_pilot_audit_event_digest(
        {
            key: value
            for key, value in candidate["sequence_zero_event"].items()
            if key != "event_digest"
        }
    )
    candidate["snapshot"]["latest_event_sequence"] = 1
    candidate["snapshot"]["latest_event_digest"] = "e" * 64
    candidate["snapshot"]["current_lifecycle_state"] = "invocation_starting"
    candidate["snapshot"]["terminal"] = False
    candidate["claim_record_bytes"] = _canonical_json_bytes(
        {
            **candidate["claim_record"],
            "_stale_marker": True,
        }
    )
    candidate["sequence_zero_event_bytes"] = _canonical_json_bytes(
        candidate["sequence_zero_event"]
    )
    candidate["snapshot_bytes"] = _canonical_json_bytes(candidate["snapshot"])
    candidate["uniqueness_entries"][0] = {
        "attempt_id": {"attempt_id": "pilot-attempt-abc123def457"}
    }

    result = validate_codex_pilot_initial_claim_committed_unit(
        candidate,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": False,
        "committed_unit_blockers": [
            "digest_mismatch",
            "history_mismatch",
            "identity_mismatch",
        ],
    }


def test_validate_codex_pilot_initial_claim_committed_unit_no_external_dependencies(monkeypatch):
    import builtins

    import phoenix_office.core.contracts as contracts

    bomb = _Bomb()
    monkeypatch.setattr(contracts, "datetime", bomb, raising=False)
    monkeypatch.setattr(contracts, "Path", bomb, raising=False)
    monkeypatch.setattr(contracts, "random", bomb, raising=False)
    monkeypatch.setattr(contracts, "subprocess", bomb, raising=False)
    monkeypatch.setattr(contracts, "socket", bomb, raising=False)
    monkeypatch.setattr(builtins, "open", bomb, raising=True)

    committed_unit, authorization = _valid_codex_pilot_committed_unit()
    result = validate_codex_pilot_initial_claim_committed_unit(
        committed_unit,
        VALID_ATTEMPT_ID,
        authorization,
    )

    assert result == {
        "committed_unit_validation_passed": True,
        "committed_unit_blockers": [],
    }
