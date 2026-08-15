"""Tests for the durable local supervised-Codex initial claim store."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

import phoenix_office.dev.codex_claim_store as claim_store_module
from phoenix_office.core import (
    codex_pilot_audit_event_digest,
    codex_pilot_authorization_fingerprint,
    compose_codex_pilot_initial_claim_bundle,
    prepare_codex_pilot_initial_claim_commit,
)
from phoenix_office.dev import SQLiteCodexPilotInitialClaimStore

VALID_ATTEMPT_ID = "pilot-attempt-abc123def456"
SECOND_ATTEMPT_ID = "pilot-attempt-def456abc789"
THIRD_ATTEMPT_ID = "pilot-attempt-ghi789abc123"

CLAIMS_TABLE = "codex_pilot_v1_initial_claims"
EVENTS_TABLE = "codex_pilot_v1_initial_audit_events"
SNAPSHOTS_TABLE = "codex_pilot_v1_initial_snapshots"
UNIQUENESS_TABLE = "codex_pilot_v1_initial_uniqueness"
LIFECYCLE_EVENTS_TABLE = "codex_pilot_v2_lifecycle_audit_events"
CURRENT_SNAPSHOTS_TABLE = "codex_pilot_v2_current_snapshots"
EXPECTED_TABLES = {
    CLAIMS_TABLE,
    EVENTS_TABLE,
    SNAPSHOTS_TABLE,
    UNIQUENESS_TABLE,
    LIFECYCLE_EVENTS_TABLE,
    CURRENT_SNAPSHOTS_TABLE,
}


def _authorization_packet(
    *,
    authorization_id: str = "pilot-auth-issue-361",
    objective: str = "Document the supervised Codex pilot authorization packet.",
) -> dict[str, object]:
    return {
        "schema_version": "codex-pilot-authorization.v1",
        "authorization_id": authorization_id,
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "decision_state": "human_authorized_for_one_run",
        "authorizer_role": "human_operator",
        "base_commit_sha": "0" * 40,
        "handoff_path": "docs/process/supervised-codex-pilot-handoff.json",
        "evidence_path": "docs/process/supervised-codex-pilot-evidence.json",
        "handoff_id": "codex-handoff-issue-361",
        "objective": objective,
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


def _prepared_commit(
    authorization: dict[str, object],
    attempt_id: str = VALID_ATTEMPT_ID,
) -> dict[str, object]:
    bundle = compose_codex_pilot_initial_claim_bundle(authorization, attempt_id)
    assert bundle["claim_bundle_passed"] is True
    preparation = prepare_codex_pilot_initial_claim_commit(bundle, authorization)
    assert preparation["prepared_commit_passed"] is True
    return preparation


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _database_hash(database_path: Path) -> str:
    return hashlib.sha256(database_path.read_bytes()).hexdigest()


def _row_counts(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        return {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in EXPECTED_TABLES
        }


def _assert_empty_store(database_path: Path) -> None:
    assert _row_counts(database_path) == {
        CLAIMS_TABLE: 0,
        EVENTS_TABLE: 0,
        SNAPSHOTS_TABLE: 0,
        UNIQUENESS_TABLE: 0,
        LIFECYCLE_EVENTS_TABLE: 0,
        CURRENT_SNAPSHOTS_TABLE: 0,
    }


def _create_valid_unit(
    database_path: Path,
) -> tuple[
    SQLiteCodexPilotInitialClaimStore,
    dict[str, object],
    dict[str, object],
]:
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "created"
    }
    return store, authorization, preparation


def test_create_read_reopen_and_exact_canonical_bytes_round_trip(tmp_path: Path):
    database_path = tmp_path / "codex-claim-state.sqlite3"
    store, authorization, preparation = _create_valid_unit(database_path)
    prepared = preparation["prepared_commit"]

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        claim_bytes = connection.execute(
            f"SELECT claim_record_bytes FROM {CLAIMS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
        event_bytes = connection.execute(
            f"SELECT sequence_zero_event_bytes FROM {EVENTS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
        snapshot_bytes = connection.execute(
            f"SELECT snapshot_bytes FROM {SNAPSHOTS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
        uniqueness = connection.execute(
            f"""
            SELECT key_kind, key_value, attempt_id
            FROM {UNIQUENESS_TABLE}
            ORDER BY CASE key_kind
                WHEN 'attempt_id' THEN 1
                WHEN 'authorization_id' THEN 2
                ELSE 3
            END
            """
        ).fetchall()
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    claim = prepared["claim_record"]
    assert tables == EXPECTED_TABLES
    assert "customers" not in tables
    assert "jobs" not in tables
    assert user_version == 2
    assert journal_mode == "delete"
    assert claim_bytes == prepared["claim_record_bytes"]
    assert event_bytes == prepared["sequence_zero_event_bytes"]
    assert snapshot_bytes == prepared["snapshot_bytes"]
    assert uniqueness == [
        ("attempt_id", VALID_ATTEMPT_ID, VALID_ATTEMPT_ID),
        ("authorization_id", claim["authorization_id"], VALID_ATTEMPT_ID),
        (
            "authorization_fingerprint",
            claim["authorization_fingerprint"],
            VALID_ATTEMPT_ID,
        ),
    ]

    durability_connection = store._connect_writable()
    try:
        assert durability_connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert durability_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert durability_connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        durability_connection.close()

    reopened = SQLiteCodexPilotInitialClaimStore(database_path)
    assert reopened.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }


def test_initialization_refuses_a_business_records_database_without_touching_it(
    tmp_path: Path,
):
    database_path = tmp_path / "business-records.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE customers (customer_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO customers VALUES ('synthetic-customer')")
        connection.commit()
    before = _database_hash(database_path)

    with pytest.raises(RuntimeError, match="^claim store initialization failed$"):
        SQLiteCodexPilotInitialClaimStore(database_path)

    assert _database_hash(database_path) == before
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT * FROM customers").fetchall() == [
            ("synthetic-customer",)
        ]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"customers"}


def test_failure_before_commit_rolls_back_every_row_and_allows_later_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_path = tmp_path / "rollback.sqlite3"
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    original_hook = store._before_commit

    def _fail_before_commit(connection: sqlite3.Connection) -> None:
        observer = sqlite3.connect(database_path)
        try:
            assert observer.execute(f"SELECT COUNT(*) FROM {CLAIMS_TABLE}").fetchone()[0] == 0
            assert observer.execute(f"SELECT COUNT(*) FROM {EVENTS_TABLE}").fetchone()[0] == 0
            assert observer.execute(f"SELECT COUNT(*) FROM {SNAPSHOTS_TABLE}").fetchone()[0] == 0
            assert (
                observer.execute(
                    f"SELECT COUNT(*) FROM {CURRENT_SNAPSHOTS_TABLE}"
                ).fetchone()[0]
                == 0
            )
            assert (
                observer.execute(
                    f"SELECT COUNT(*) FROM {LIFECYCLE_EVENTS_TABLE}"
                ).fetchone()[0]
                == 0
            )
            assert (
                observer.execute(f"SELECT COUNT(*) FROM {UNIQUENESS_TABLE}").fetchone()[0]
                == 0
            )
        finally:
            observer.close()
        del connection
        raise RuntimeError("injected pre-commit failure")

    monkeypatch.setattr(store, "_before_commit", _fail_before_commit)
    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "commit_incomplete"
    }
    _assert_empty_store(database_path)

    monkeypatch.setattr(store, "_before_commit", original_hook)
    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "created"
    }


def test_attempt_id_conflict_is_reported_before_other_uniqueness_keys(tmp_path: Path):
    store, first_authorization, first_preparation = _create_valid_unit(
        tmp_path / "attempt-conflict.sqlite3"
    )
    second_authorization = _authorization_packet(
        authorization_id="pilot-auth-issue-362",
        objective="Document a second supervised Codex authorization packet.",
    )
    second_preparation = _prepared_commit(second_authorization, VALID_ATTEMPT_ID)

    assert store.create_initial_claim_commit(second_preparation, second_authorization) == {
        "claim_store_create_category": "attempt_id_conflict"
    }
    assert store.create_initial_claim_commit(first_preparation, first_authorization) == {
        "claim_store_create_category": "attempt_id_conflict"
    }


def test_authorization_id_conflict_precedes_fingerprint_conflict(tmp_path: Path):
    database_path = tmp_path / "authorization-conflict.sqlite3"
    store, _, _ = _create_valid_unit(database_path)
    second_authorization = _authorization_packet(
        objective="Document a changed supervised Codex authorization objective."
    )
    second_preparation = _prepared_commit(second_authorization, SECOND_ATTEMPT_ID)

    assert store.create_initial_claim_commit(second_preparation, second_authorization) == {
        "claim_store_create_category": "authorization_id_conflict"
    }
    assert _row_counts(database_path) == {
        CLAIMS_TABLE: 1,
        EVENTS_TABLE: 1,
        SNAPSHOTS_TABLE: 1,
        UNIQUENESS_TABLE: 3,
        LIFECYCLE_EVENTS_TABLE: 0,
        CURRENT_SNAPSHOTS_TABLE: 1,
    }


def test_authorization_fingerprint_conflict_is_classified_independently(tmp_path: Path):
    database_path = tmp_path / "fingerprint-conflict.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet(
        authorization_id="pilot-auth-issue-363",
        objective="Document a third supervised Codex authorization packet.",
    )
    preparation = _prepared_commit(authorization, SECOND_ATTEMPT_ID)
    fingerprint = codex_pilot_authorization_fingerprint(authorization)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"""
            INSERT INTO {UNIQUENESS_TABLE} (key_kind, key_value, attempt_id)
            VALUES ('authorization_fingerprint', ?, ?)
            """,
            (fingerprint, THIRD_ATTEMPT_ID),
        )
        connection.commit()

    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "authorization_fingerprint_conflict"
    }
    assert _row_counts(database_path) == {
        CLAIMS_TABLE: 0,
        EVENTS_TABLE: 0,
        SNAPSHOTS_TABLE: 0,
        UNIQUENESS_TABLE: 1,
        LIFECYCLE_EVENTS_TABLE: 0,
        CURRENT_SNAPSHOTS_TABLE: 0,
    }


def test_multiple_simultaneous_conflicts_use_required_precedence(tmp_path: Path):
    store, authorization, preparation = _create_valid_unit(
        tmp_path / "multiple-conflicts.sqlite3"
    )
    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "attempt_id_conflict"
    }

    same_authorization_new_attempt = _prepared_commit(authorization, SECOND_ATTEMPT_ID)
    assert store.create_initial_claim_commit(
        same_authorization_new_attempt,
        authorization,
    ) == {"claim_store_create_category": "authorization_id_conflict"}


def test_concurrent_competing_creates_have_exactly_one_winner(tmp_path: Path):
    database_path = tmp_path / "concurrent.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    competitors = 4
    barrier = Barrier(competitors)

    def _compete() -> str:
        barrier.wait()
        result = store.create_initial_claim_commit(preparation, authorization)
        return result["claim_store_create_category"]

    with ThreadPoolExecutor(max_workers=competitors) as executor:
        categories = list(executor.map(lambda _: _compete(), range(competitors)))

    assert categories.count("created") == 1
    assert categories.count("attempt_id_conflict") == competitors - 1
    assert _row_counts(database_path) == {
        CLAIMS_TABLE: 1,
        EVENTS_TABLE: 1,
        SNAPSHOTS_TABLE: 1,
        UNIQUENESS_TABLE: 3,
        LIFECYCLE_EVENTS_TABLE: 0,
        CURRENT_SNAPSHOTS_TABLE: 1,
    }


@pytest.mark.parametrize(
    "failure_case, expected_category",
    [
        ("invalid_authorization", "authorization_context_invalid"),
        ("stale_authorization", "bundle_binding_mismatch"),
        ("objective_drift", "bundle_binding_mismatch"),
        ("fingerprint_drift", "bundle_binding_mismatch"),
        ("projection_mismatch", "bundle_binding_mismatch"),
    ],
)
def test_authorization_and_binding_failures_reject_before_durable_mutation(
    tmp_path: Path,
    failure_case: str,
    expected_category: str,
):
    database_path = tmp_path / f"{failure_case}.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    trusted_authorization = copy.deepcopy(authorization)
    candidate_preparation = copy.deepcopy(preparation)

    if failure_case == "invalid_authorization":
        trusted_authorization.pop("authorizer_role")
    elif failure_case == "stale_authorization":
        trusted_authorization["base_commit_sha"] = "1" * 40
    elif failure_case == "objective_drift":
        trusted_authorization["objective"] = (
            "Document a drifted supervised Codex authorization objective."
        )
    elif failure_case == "fingerprint_drift":
        claim = candidate_preparation["prepared_commit"]["claim_record"]
        claim["authorization_fingerprint"] = "1" * 64
        candidate_preparation["prepared_commit"]["claim_record_bytes"] = _canonical_bytes(
            claim
        )
    else:
        claim = candidate_preparation["prepared_commit"]["claim_record"]
        claim["expected_pr_title"] = "docs: drifted supervised Codex title"
        candidate_preparation["prepared_commit"]["claim_record_bytes"] = _canonical_bytes(
            claim
        )

    assert store.create_initial_claim_commit(
        candidate_preparation,
        trusted_authorization,
    ) == {"claim_store_create_category": expected_category}
    _assert_empty_store(database_path)


def test_authorization_fingerprint_is_explicitly_recomputed_before_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_path = tmp_path / "fingerprint-recomputed.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    calls: list[object] = []
    original = claim_store_module.codex_pilot_authorization_fingerprint

    def _record_call(package: object) -> str:
        calls.append(package)
        return original(package)

    monkeypatch.setattr(
        claim_store_module,
        "codex_pilot_authorization_fingerprint",
        _record_call,
    )
    assert store.create_initial_claim_commit(preparation, authorization) == {
        "claim_store_create_category": "created"
    }
    assert len(calls) == 1
    assert calls[0] is not authorization


def test_invalid_prepared_unit_is_rejected_without_rows(tmp_path: Path):
    database_path = tmp_path / "invalid-prepared.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()

    assert store.create_initial_claim_commit({"unexpected": True}, authorization) == {
        "claim_store_create_category": "bundle_invalid"
    }
    _assert_empty_store(database_path)


def test_invalid_and_missing_attempt_reads_are_bounded_and_sanitized(tmp_path: Path):
    database_path = tmp_path / "missing.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()
    unsafe_selector = "private-path-marker/attempt"

    invalid = store.read_initial_claim_bundle(unsafe_selector, authorization)
    missing = store.read_initial_claim_bundle(SECOND_ATTEMPT_ID, authorization)

    assert invalid == {"claim_store_read_category": "attempt_id_invalid"}
    assert missing == {"claim_store_read_category": "missing_commit"}
    assert unsafe_selector not in json.dumps(invalid)
    _assert_empty_store(database_path)


def test_wrong_trusted_authorization_is_rejected(tmp_path: Path):
    database_path = tmp_path / "wrong-authorization.sqlite3"
    store, _, _ = _create_valid_unit(database_path)
    wrong_authorization = _authorization_packet(
        authorization_id="pilot-auth-issue-364",
        objective="Document another supervised Codex authorization packet.",
    )
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, wrong_authorization) == {
        "claim_store_read_category": "bundle_binding_mismatch"
    }
    assert _database_hash(database_path) == before


@pytest.mark.parametrize(
    "record_kind, expected_category",
    [
        ("claim", "claim_record_corrupt"),
        ("event", "audit_event_corrupt"),
        ("snapshot", "snapshot_corrupt"),
    ],
)
def test_record_corruption_fails_closed_without_repair(
    tmp_path: Path,
    record_kind: str,
    expected_category: str,
):
    database_path = tmp_path / f"{record_kind}-corrupt.sqlite3"
    store, authorization, _ = _create_valid_unit(database_path)
    update_by_kind = {
        "claim": (CLAIMS_TABLE, "claim_record_bytes"),
        "event": (EVENTS_TABLE, "sequence_zero_event_bytes"),
        "snapshot": (SNAPSHOTS_TABLE, "snapshot_bytes"),
    }
    table_name, column_name = update_by_kind[record_kind]
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {table_name} SET {column_name} = ? WHERE attempt_id = ?",
            (sqlite3.Binary(b"{}"), VALID_ATTEMPT_ID),
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": expected_category
    }
    assert _database_hash(database_path) == before


def test_uniqueness_corruption_fails_closed_without_repair(tmp_path: Path):
    database_path = tmp_path / "uniqueness-corrupt.sqlite3"
    store, authorization, _ = _create_valid_unit(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"DELETE FROM {UNIQUENESS_TABLE} WHERE key_kind = 'authorization_id'"
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "uniqueness_entry_corrupt"
    }
    assert _database_hash(database_path) == before
    assert _row_counts(database_path)[UNIQUENESS_TABLE] == 2


def test_noncanonical_record_bytes_are_digest_mismatch_and_not_rewritten(tmp_path: Path):
    database_path = tmp_path / "digest-mismatch.sqlite3"
    store, authorization, preparation = _create_valid_unit(database_path)
    pretty_bytes = json.dumps(
        preparation["prepared_commit"]["claim_record"],
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {CLAIMS_TABLE} SET claim_record_bytes = ? WHERE attempt_id = ?",
            (sqlite3.Binary(pretty_bytes), VALID_ATTEMPT_ID),
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "digest_mismatch"
    }
    assert _database_hash(database_path) == before
    with sqlite3.connect(database_path) as connection:
        stored = connection.execute(
            f"SELECT claim_record_bytes FROM {CLAIMS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
    assert stored == pretty_bytes


def test_identity_mismatch_is_detected_without_repair(tmp_path: Path):
    database_path = tmp_path / "identity-mismatch.sqlite3"
    store, authorization, preparation = _create_valid_unit(database_path)
    event = copy.deepcopy(preparation["prepared_commit"]["sequence_zero_event"])
    snapshot = copy.deepcopy(preparation["prepared_commit"]["snapshot"])
    event["authorization_id"] = "pilot-auth-identity-drift"
    event["event_digest"] = codex_pilot_audit_event_digest(
        {key: value for key, value in event.items() if key != "event_digest"}
    )
    snapshot["latest_event_digest"] = event["event_digest"]
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {EVENTS_TABLE} SET sequence_zero_event_bytes = ? WHERE attempt_id = ?",
            (sqlite3.Binary(_canonical_bytes(event)), VALID_ATTEMPT_ID),
        )
        connection.execute(
            f"UPDATE {SNAPSHOTS_TABLE} SET snapshot_bytes = ? WHERE attempt_id = ?",
            (sqlite3.Binary(_canonical_bytes(snapshot)), VALID_ATTEMPT_ID),
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "identity_mismatch"
    }
    assert _database_hash(database_path) == before


def test_history_mismatch_is_detected_without_repair(tmp_path: Path):
    database_path = tmp_path / "history-mismatch.sqlite3"
    store, authorization, preparation = _create_valid_unit(database_path)
    event = copy.deepcopy(preparation["prepared_commit"]["sequence_zero_event"])
    snapshot = copy.deepcopy(preparation["prepared_commit"]["snapshot"])
    previous_digest = event["event_digest"]
    event.update(
        {
            "event_sequence": 1,
            "previous_lifecycle_state": "claim_created",
            "next_lifecycle_state": "invocation_starting",
            "event_category": "invocation_starting",
            "result_category": "started",
            "actor_role": "phoenix_gate",
            "previous_event_digest": previous_digest,
        }
    )
    event["event_digest"] = codex_pilot_audit_event_digest(
        {key: value for key, value in event.items() if key != "event_digest"}
    )
    snapshot.update(
        {
            "latest_event_sequence": 1,
            "latest_event_digest": event["event_digest"],
            "current_lifecycle_state": "invocation_starting",
            "terminal": False,
        }
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {EVENTS_TABLE} SET sequence_zero_event_bytes = ? WHERE attempt_id = ?",
            (sqlite3.Binary(_canonical_bytes(event)), VALID_ATTEMPT_ID),
        )
        connection.execute(
            f"UPDATE {SNAPSHOTS_TABLE} SET snapshot_bytes = ? WHERE attempt_id = ?",
            (sqlite3.Binary(_canonical_bytes(snapshot)), VALID_ATTEMPT_ID),
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "history_mismatch"
    }
    assert _database_hash(database_path) == before


def test_results_never_echo_sensitive_inputs_or_database_path(tmp_path: Path):
    database_path = tmp_path / "sensitive-marker.sqlite3"
    store = SQLiteCodexPilotInitialClaimStore(database_path)
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    unsafe_authorization = copy.deepcopy(authorization)
    unsafe_marker = "credential-marker-must-not-echo"
    unsafe_authorization["objective"] = unsafe_marker

    create_result = store.create_initial_claim_commit(preparation, unsafe_authorization)
    read_result = store.read_initial_claim_bundle("invalid-selector", unsafe_authorization)
    output = json.dumps([create_result, read_result], sort_keys=True)

    assert create_result == {"claim_store_create_category": "authorization_context_invalid"}
    assert read_result == {"claim_store_read_category": "attempt_id_invalid"}
    assert unsafe_marker not in output
    assert str(database_path) not in output


def test_no_sqlite_sidecars_remain_after_create_read_and_reopen(tmp_path: Path):
    database_path = tmp_path / "sidecars.sqlite3"
    store, authorization, _ = _create_valid_unit(database_path)
    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }
    reopened = SQLiteCodexPilotInitialClaimStore(database_path)
    assert reopened.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }

    assert not Path(f"{database_path}-wal").exists()
    assert not Path(f"{database_path}-shm").exists()
    assert not Path(f"{database_path}-journal").exists()


def test_lifecycle_append_is_contiguous_atomic_and_survives_reopen(tmp_path: Path):
    database_path = tmp_path / "lifecycle.sqlite3"
    store, authorization, preparation = _create_valid_unit(database_path)
    initial_claim_bytes = preparation["prepared_commit"]["claim_record_bytes"]
    initial_snapshot_bytes = preparation["prepared_commit"]["snapshot_bytes"]

    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=0,
        expected_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
    ) == {
        "lifecycle_append_category": "appended",
        "event_sequence": 1,
        "lifecycle_state": "invocation_starting",
    }
    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=1,
        expected_lifecycle_state="invocation_starting",
        next_lifecycle_state="invocation_started",
    )["lifecycle_append_category"] == "appended"
    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=2,
        expected_lifecycle_state="invocation_started",
        next_lifecycle_state="pr_opened_and_stopped",
        branch_identity="codex/supervised-pilot-authorization",
        pull_request_identity="pr-400",
        usage_category="within_budget",
    )["lifecycle_append_category"] == "appended"

    reopened = SQLiteCodexPilotInitialClaimStore(database_path)
    lifecycle = reopened.read_lifecycle_state(VALID_ATTEMPT_ID, authorization)
    assert lifecycle["lifecycle_read_category"] == "read_success"
    assert [event["event_sequence"] for event in lifecycle["audit_events"]] == [
        0,
        1,
        2,
        3,
    ]
    assert lifecycle["snapshot"]["current_lifecycle_state"] == "pr_opened_and_stopped"
    assert lifecycle["snapshot"]["latest_event_sequence"] == 3
    assert lifecycle["snapshot"]["branch_identity"] == (
        "codex/supervised-pilot-authorization"
    )
    assert lifecycle["snapshot"]["pull_request_identity"] == "pr-400"

    with sqlite3.connect(database_path) as connection:
        claim_bytes = connection.execute(
            f"SELECT claim_record_bytes FROM {CLAIMS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
        stored_initial_snapshot = connection.execute(
            f"SELECT snapshot_bytes FROM {SNAPSHOTS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
        later_count = connection.execute(
            f"SELECT COUNT(*) FROM {LIFECYCLE_EVENTS_TABLE} WHERE attempt_id = ?",
            (VALID_ATTEMPT_ID,),
        ).fetchone()[0]
    assert claim_bytes == initial_claim_bytes
    assert stored_initial_snapshot == initial_snapshot_bytes
    assert later_count == 3
    assert reopened.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }
    assert not Path(f"{database_path}-wal").exists()
    assert not Path(f"{database_path}-shm").exists()
    assert not Path(f"{database_path}-journal").exists()


def test_lifecycle_append_rollback_preserves_prior_event_and_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_path = tmp_path / "lifecycle-rollback.sqlite3"
    store, authorization, _ = _create_valid_unit(database_path)
    before = store.read_lifecycle_state(VALID_ATTEMPT_ID, authorization)
    assert before["lifecycle_read_category"] == "read_success"

    def _fail_before_commit(_connection: sqlite3.Connection) -> None:
        raise RuntimeError("injected lifecycle failure")

    monkeypatch.setattr(store, "_before_lifecycle_commit", _fail_before_commit)
    result = store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=0,
        expected_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
    )
    assert result["lifecycle_append_category"] == "commit_incomplete"
    after = store.read_lifecycle_state(VALID_ATTEMPT_ID, authorization)
    assert after == before
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            f"SELECT COUNT(*) FROM {LIFECYCLE_EVENTS_TABLE}"
        ).fetchone()[0] == 0


def test_stale_and_terminal_lifecycle_appends_fail_closed(tmp_path: Path):
    store, authorization, _ = _create_valid_unit(tmp_path / "lifecycle-terminal.sqlite3")
    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=0,
        expected_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
    )["lifecycle_append_category"] == "appended"

    stale = store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=0,
        expected_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
    )
    assert stale["lifecycle_append_category"] == "stale_append_rejected"

    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=1,
        expected_lifecycle_state="invocation_starting",
        next_lifecycle_state="failed",
        recovery_category="operator_recovery",
    )["lifecycle_append_category"] == "appended"
    terminal = store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=2,
        expected_lifecycle_state="failed",
        next_lifecycle_state="invocation_starting",
    )
    assert terminal["lifecycle_append_category"] == "terminal_append_rejected"


def _create_exact_v1_database(
    database_path: Path,
    authorization: dict[str, object],
    preparation: dict[str, object],
) -> None:
    prepared = preparation["prepared_commit"]
    claim = prepared["claim_record"]
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        for statement in claim_store_module._V1_CREATE_STATEMENTS.values():
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            f"INSERT INTO {CLAIMS_TABLE} VALUES (?, ?)",
            (VALID_ATTEMPT_ID, sqlite3.Binary(prepared["claim_record_bytes"])),
        )
        connection.execute(
            f"INSERT INTO {EVENTS_TABLE} VALUES (?, 0, ?)",
            (
                VALID_ATTEMPT_ID,
                sqlite3.Binary(prepared["sequence_zero_event_bytes"]),
            ),
        )
        connection.execute(
            f"INSERT INTO {SNAPSHOTS_TABLE} VALUES (?, ?)",
            (VALID_ATTEMPT_ID, sqlite3.Binary(prepared["snapshot_bytes"])),
        )
        uniqueness_values = {
            "attempt_id": VALID_ATTEMPT_ID,
            "authorization_id": claim["authorization_id"],
            "authorization_fingerprint": claim["authorization_fingerprint"],
        }
        connection.executemany(
            f"INSERT INTO {UNIQUENESS_TABLE} VALUES (?, ?, ?)",
            [
                (key, value, VALID_ATTEMPT_ID)
                for key, value in uniqueness_values.items()
            ],
        )
        connection.commit()
    del authorization


def test_exact_task_059_v1_database_migrates_atomically_to_v2(tmp_path: Path):
    database_path = tmp_path / "task-059-v1.sqlite3"
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    _create_exact_v1_database(database_path, authorization, preparation)

    store = SQLiteCodexPilotInitialClaimStore(database_path)
    assert store.read_initial_claim_bundle(VALID_ATTEMPT_ID, authorization) == {
        "claim_store_read_category": "read_success"
    }
    lifecycle = store.read_lifecycle_state(VALID_ATTEMPT_ID, authorization)
    assert lifecycle["lifecycle_read_category"] == "read_success"
    assert lifecycle["snapshot"]["latest_event_sequence"] == 0
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if not row[0].startswith("sqlite_")
        }
    assert tables == EXPECTED_TABLES


def test_failed_v1_migration_rolls_back_to_exact_v1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_path = tmp_path / "task-059-v1-rollback.sqlite3"
    authorization = _authorization_packet()
    preparation = _prepared_commit(authorization)
    _create_exact_v1_database(database_path, authorization, preparation)

    def _fail_migration(_self, _connection: sqlite3.Connection) -> None:
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(
        SQLiteCodexPilotInitialClaimStore,
        "_before_migration_commit",
        _fail_migration,
    )
    with pytest.raises(RuntimeError, match="claim store initialization failed"):
        SQLiteCodexPilotInitialClaimStore(database_path)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if not row[0].startswith("sqlite_")
        }
    assert tables == set(claim_store_module._V1_CREATE_STATEMENTS)


def test_lifecycle_corruption_is_detected_without_repair(tmp_path: Path):
    database_path = tmp_path / "lifecycle-corrupt.sqlite3"
    store, authorization, _ = _create_valid_unit(database_path)
    assert store.append_lifecycle_event(
        VALID_ATTEMPT_ID,
        authorization,
        expected_event_sequence=0,
        expected_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
    )["lifecycle_append_category"] == "appended"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"UPDATE {LIFECYCLE_EVENTS_TABLE} SET event_bytes = ?",
            (sqlite3.Binary(b"{}"),),
        )
        connection.commit()
    before = _database_hash(database_path)

    assert store.read_lifecycle_state(VALID_ATTEMPT_ID, authorization)[
        "lifecycle_read_category"
    ] == "committed_unit_invalid"
    assert _database_hash(database_path) == before
