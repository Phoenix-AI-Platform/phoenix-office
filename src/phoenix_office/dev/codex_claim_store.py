"""Durable local SQLite storage for supervised-Codex claim lifecycle state."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from copy import deepcopy
from pathlib import Path
from typing import Final

from phoenix_office.core import (
    classify_codex_pilot_initial_claim_conflicts,
    classify_codex_pilot_initial_claim_read_outcome,
    codex_pilot_audit_event_digest,
    codex_pilot_authorization_fingerprint,
    derive_codex_pilot_attempt_snapshot,
    validate_codex_pilot_attempt_snapshot_binding,
    validate_codex_pilot_audit_event_binding,
    validate_codex_pilot_audit_event_record,
    validate_codex_pilot_authorization_packet,
    validate_codex_pilot_initial_claim_committed_unit,
    validate_codex_pilot_initial_claim_read_request,
    validate_codex_pilot_initial_claim_store_create_result,
    validate_codex_pilot_initial_claim_store_read_result,
    validate_codex_pilot_prepared_initial_claim_commit,
)
from phoenix_office.core.contracts import (
    CODEX_PILOT_AUDIT_EVENT_SCHEMA_VERSION,
    CODEX_PILOT_AUDIT_EVENT_TRANSITIONS,
)

CONTROL_STATE_SCHEMA_VERSION: Final = 2
_SCHEMA_VERSION: Final = CONTROL_STATE_SCHEMA_VERSION
_CLAIMS_TABLE: Final = "codex_pilot_v1_initial_claims"
_EVENTS_TABLE: Final = "codex_pilot_v1_initial_audit_events"
_SNAPSHOTS_TABLE: Final = "codex_pilot_v1_initial_snapshots"
_UNIQUENESS_TABLE: Final = "codex_pilot_v1_initial_uniqueness"
_LIFECYCLE_EVENTS_TABLE: Final = "codex_pilot_v2_lifecycle_audit_events"
_CURRENT_SNAPSHOTS_TABLE: Final = "codex_pilot_v2_current_snapshots"
_UNIQUENESS_KEYS: Final = (
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint",
)

_V1_CREATE_STATEMENTS: Final = {
    _CLAIMS_TABLE: f"""
        CREATE TABLE {_CLAIMS_TABLE} (
            attempt_id TEXT NOT NULL PRIMARY KEY,
            claim_record_bytes BLOB NOT NULL
        ) WITHOUT ROWID
    """,
    _EVENTS_TABLE: f"""
        CREATE TABLE {_EVENTS_TABLE} (
            attempt_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL CHECK (event_sequence = 0),
            sequence_zero_event_bytes BLOB NOT NULL,
            PRIMARY KEY (attempt_id, event_sequence),
            FOREIGN KEY (attempt_id) REFERENCES {_CLAIMS_TABLE} (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) WITHOUT ROWID
    """,
    _SNAPSHOTS_TABLE: f"""
        CREATE TABLE {_SNAPSHOTS_TABLE} (
            attempt_id TEXT NOT NULL PRIMARY KEY,
            snapshot_bytes BLOB NOT NULL,
            FOREIGN KEY (attempt_id) REFERENCES {_CLAIMS_TABLE} (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) WITHOUT ROWID
    """,
    _UNIQUENESS_TABLE: f"""
        CREATE TABLE {_UNIQUENESS_TABLE} (
            key_kind TEXT NOT NULL CHECK (
                key_kind IN ('attempt_id', 'authorization_id', 'authorization_fingerprint')
            ),
            key_value TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            PRIMARY KEY (key_kind, key_value),
            UNIQUE (attempt_id, key_kind),
            FOREIGN KEY (attempt_id) REFERENCES {_CLAIMS_TABLE} (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) WITHOUT ROWID
    """,
}
_V2_EXTENSION_CREATE_STATEMENTS: Final = {
    _LIFECYCLE_EVENTS_TABLE: f"""
        CREATE TABLE {_LIFECYCLE_EVENTS_TABLE} (
            attempt_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL CHECK (event_sequence >= 1),
            event_bytes BLOB NOT NULL,
            PRIMARY KEY (attempt_id, event_sequence),
            FOREIGN KEY (attempt_id) REFERENCES {_CLAIMS_TABLE} (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) WITHOUT ROWID
    """,
    _CURRENT_SNAPSHOTS_TABLE: f"""
        CREATE TABLE {_CURRENT_SNAPSHOTS_TABLE} (
            attempt_id TEXT NOT NULL PRIMARY KEY,
            snapshot_bytes BLOB NOT NULL,
            FOREIGN KEY (attempt_id) REFERENCES {_CLAIMS_TABLE} (attempt_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT
        ) WITHOUT ROWID
    """,
}
_CREATE_STATEMENTS: Final = {
    **_V1_CREATE_STATEMENTS,
    **_V2_EXTENSION_CREATE_STATEMENTS,
}
_EXPECTED_TABLES: Final = frozenset(_CREATE_STATEMENTS)
_LIFECYCLE_TERMINAL_STATES: Final = {
    "aborted",
    "failed",
    "cancelled",
    "timed_out",
    "completed_pending_review",
}
_LIFECYCLE_APPEND_CATEGORIES: Final = {
    "appended",
    "attempt_id_invalid",
    "authorization_context_invalid",
    "missing_commit",
    "committed_unit_invalid",
    "stale_append_rejected",
    "terminal_append_rejected",
    "event_invalid",
    "claim_store_unavailable",
    "claim_durability_uncertain",
    "commit_incomplete",
}
_LIFECYCLE_READ_CATEGORIES: Final = {
    "read_success",
    "attempt_id_invalid",
    "authorization_context_invalid",
    "missing_commit",
    "committed_unit_invalid",
    "claim_store_unavailable",
}


class _InitializationFailure(Exception):
    """Internal sanitized initialization failure."""


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


def _create_result(category: str) -> dict[str, str]:
    result = {"claim_store_create_category": category}
    validation = validate_codex_pilot_initial_claim_store_create_result(result)
    if validation["claim_store_create_result_valid"]:
        return result
    return {"claim_store_create_category": "claim_store_unavailable"}


def _read_result(category: str) -> dict[str, str]:
    result = {"claim_store_read_category": category}
    validation = validate_codex_pilot_initial_claim_store_read_result(result)
    if validation["claim_store_read_result_valid"]:
        return result
    return {"claim_store_read_category": "claim_store_unavailable"}


def _decode_json_record(value: object) -> object:
    if type(value) is not bytes:
        return None
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _lifecycle_append_result(
    category: str,
    *,
    event_sequence: int | None = None,
    lifecycle_state: str | None = None,
) -> dict[str, object]:
    if category not in _LIFECYCLE_APPEND_CATEGORIES:
        category = "claim_store_unavailable"
    return {
        "lifecycle_append_category": category,
        "event_sequence": event_sequence,
        "lifecycle_state": lifecycle_state,
    }


def _lifecycle_read_result(
    category: str,
    *,
    claim_record: object = None,
    audit_events: object = None,
    snapshot: object = None,
) -> dict[str, object]:
    if category not in _LIFECYCLE_READ_CATEGORIES:
        category = "claim_store_unavailable"
    return {
        "lifecycle_read_category": category,
        "claim_record": claim_record,
        "audit_events": audit_events,
        "snapshot": snapshot,
    }


class SQLiteCodexPilotInitialClaimStore:
    """Atomic create/read/lifecycle adapter for dedicated local control state."""

    def __init__(self, database_path: str | Path) -> None:
        try:
            self._database_path = Path(database_path)
        except (TypeError, ValueError):
            raise RuntimeError("claim store initialization failed") from None
        self._initialize_database()

    def create_initial_claim_commit(
        self,
        preparation_result: object,
        authorization_package: object,
    ) -> object:
        """Atomically create one fully validated initial claim unit."""

        try:
            trusted_authorization = deepcopy(authorization_package)
        except Exception:
            return _create_result("authorization_context_invalid")

        authorization_validation = validate_codex_pilot_authorization_packet(
            trusted_authorization
        )
        if not authorization_validation["authorization_structural_valid"]:
            return _create_result("authorization_context_invalid")
        try:
            authorization_fingerprint = codex_pilot_authorization_fingerprint(
                trusted_authorization
            )
        except (TypeError, ValueError):
            return _create_result("authorization_context_invalid")

        try:
            prepared_snapshot = deepcopy(preparation_result)
        except Exception:
            return _create_result("bundle_invalid")
        prepared_validation = validate_codex_pilot_prepared_initial_claim_commit(
            prepared_snapshot,
            trusted_authorization,
        )
        if not prepared_validation["prepared_commit_structural_valid"]:
            if "authorization_package_invalid" in prepared_validation[
                "prepared_commit_blockers"
            ]:
                return _create_result("authorization_context_invalid")
            return _create_result("bundle_invalid")
        if not prepared_validation["prepared_commit_binding_passed"]:
            return _create_result("bundle_binding_mismatch")

        prepared_commit = prepared_snapshot["prepared_commit"]
        claim_record = prepared_commit["claim_record"]
        if claim_record["authorization_fingerprint"] != authorization_fingerprint:
            return _create_result("bundle_binding_mismatch")

        attempt_id = claim_record["attempt_id"]
        authorization_id = claim_record["authorization_id"]
        uniqueness_values = {
            "attempt_id": attempt_id,
            "authorization_id": authorization_id,
            "authorization_fingerprint": authorization_fingerprint,
        }

        connection: sqlite3.Connection | None = None
        transaction_started = False
        commit_started = False
        try:
            connection = self._connect_writable()
            connection.execute("BEGIN IMMEDIATE")
            transaction_started = True

            conflict_observation = {
                f"{key_kind}_conflict": self._uniqueness_exists(
                    connection,
                    key_kind,
                    uniqueness_values[key_kind],
                )
                for key_kind in _UNIQUENESS_KEYS
            }
            conflict = classify_codex_pilot_initial_claim_conflicts(
                prepared_snapshot,
                trusted_authorization,
                conflict_observation,
            )
            if not conflict["conflict_classification_passed"]:
                connection.execute("ROLLBACK")
                return _create_result("bundle_binding_mismatch")
            if conflict["conflict_detected"]:
                connection.execute("ROLLBACK")
                return _create_result(str(conflict["conflict_category"]))

            connection.execute(
                f"INSERT INTO {_CLAIMS_TABLE} (attempt_id, claim_record_bytes) VALUES (?, ?)",
                (attempt_id, sqlite3.Binary(prepared_commit["claim_record_bytes"])),
            )
            connection.execute(
                f"""
                INSERT INTO {_EVENTS_TABLE} (
                    attempt_id,
                    event_sequence,
                    sequence_zero_event_bytes
                ) VALUES (?, 0, ?)
                """,
                (
                    attempt_id,
                    sqlite3.Binary(prepared_commit["sequence_zero_event_bytes"]),
                ),
            )
            connection.execute(
                f"INSERT INTO {_SNAPSHOTS_TABLE} (attempt_id, snapshot_bytes) VALUES (?, ?)",
                (attempt_id, sqlite3.Binary(prepared_commit["snapshot_bytes"])),
            )
            connection.execute(
                f"""
                INSERT INTO {_CURRENT_SNAPSHOTS_TABLE} (attempt_id, snapshot_bytes)
                VALUES (?, ?)
                """,
                (attempt_id, sqlite3.Binary(prepared_commit["snapshot_bytes"])),
            )
            connection.executemany(
                f"""
                INSERT INTO {_UNIQUENESS_TABLE} (key_kind, key_value, attempt_id)
                VALUES (?, ?, ?)
                """,
                [
                    (key_kind, uniqueness_values[key_kind], attempt_id)
                    for key_kind in _UNIQUENESS_KEYS
                ],
            )

            self._before_commit(connection)
            commit_started = True
            connection.execute("COMMIT")
        except sqlite3.Error:
            self._rollback_quietly(connection)
            if commit_started:
                category = "claim_durability_uncertain"
            elif transaction_started:
                category = "commit_incomplete"
            else:
                category = "claim_store_unavailable"
            return _create_result(category)
        except Exception:
            self._rollback_quietly(connection)
            category = "commit_incomplete" if transaction_started else "claim_store_unavailable"
            return _create_result(category)
        finally:
            if connection is not None:
                connection.close()

        return _create_result("created")

    def append_lifecycle_event(
        self,
        attempt_id: object,
        authorization_package: object,
        *,
        expected_event_sequence: object,
        expected_lifecycle_state: object,
        next_lifecycle_state: object,
        branch_identity: object = None,
        pull_request_identity: object = None,
        usage_category: object = None,
        timeout_category: object = None,
        cancellation_category: object = None,
        final_ci_category: object = None,
        assistant_review_verdict: object = None,
        recovery_category: object = None,
    ) -> dict[str, object]:
        """Atomically append one validated event and replace the derived snapshot."""

        try:
            trusted_authorization = deepcopy(authorization_package)
        except Exception:
            return _lifecycle_append_result("authorization_context_invalid")
        request = validate_codex_pilot_initial_claim_read_request(
            attempt_id,
            trusted_authorization,
        )
        if not request["attempt_id_valid"]:
            return _lifecycle_append_result("attempt_id_invalid")
        if not request["authorization_context_valid"]:
            return _lifecycle_append_result("authorization_context_invalid")
        if type(expected_event_sequence) is not int or expected_event_sequence < 0:
            return _lifecycle_append_result("stale_append_rejected")
        if type(expected_lifecycle_state) is not str:
            return _lifecycle_append_result("stale_append_rejected")
        if type(next_lifecycle_state) is not str:
            return _lifecycle_append_result("event_invalid")

        optional_values = {
            "branch_identity": branch_identity,
            "pull_request_identity": pull_request_identity,
            "usage_category": usage_category,
            "timeout_category": timeout_category,
            "cancellation_category": cancellation_category,
            "final_ci_category": final_ci_category,
            "assistant_review_verdict": assistant_review_verdict,
            "recovery_category": recovery_category,
        }

        connection: sqlite3.Connection | None = None
        transaction_started = False
        commit_started = False
        try:
            connection = self._connect_writable()
            connection.execute("BEGIN IMMEDIATE")
            transaction_started = True
            lifecycle_unit = self._load_lifecycle_unit(connection, attempt_id)
            if lifecycle_unit is None:
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("missing_commit")
            validated = self._validated_lifecycle_unit(
                lifecycle_unit,
                attempt_id,
                trusted_authorization,
            )
            if validated is None:
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("committed_unit_invalid")
            claim_record, audit_events, snapshot = validated
            current_sequence = snapshot["latest_event_sequence"]
            current_state = snapshot["current_lifecycle_state"]
            if (
                current_sequence != expected_event_sequence
                or current_state != expected_lifecycle_state
            ):
                connection.execute("ROLLBACK")
                return _lifecycle_append_result(
                    "stale_append_rejected",
                    event_sequence=current_sequence,
                    lifecycle_state=current_state,
                )
            if snapshot["terminal"] or current_state in _LIFECYCLE_TERMINAL_STATES:
                connection.execute("ROLLBACK")
                return _lifecycle_append_result(
                    "terminal_append_rejected",
                    event_sequence=current_sequence,
                    lifecycle_state=current_state,
                )

            transition = CODEX_PILOT_AUDIT_EVENT_TRANSITIONS.get(
                (current_state, next_lifecycle_state)
            )
            if transition is None:
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("event_invalid")
            previous_event = audit_events[-1]
            event: dict[str, object] = {
                "schema_version": CODEX_PILOT_AUDIT_EVENT_SCHEMA_VERSION,
                "attempt_id": claim_record["attempt_id"],
                "authorization_id": claim_record["authorization_id"],
                "authorization_fingerprint": claim_record[
                    "authorization_fingerprint"
                ],
                "event_sequence": current_sequence + 1,
                "previous_lifecycle_state": current_state,
                "next_lifecycle_state": next_lifecycle_state,
                "event_category": transition["event_category"],
                "result_category": transition["result_category"],
                "actor_role": transition["actor_role"],
                "codex_approved": False,
                "codex_merged": False,
                "previous_event_digest": previous_event["event_digest"],
            }
            for field_name, value in optional_values.items():
                if value is not None:
                    event[field_name] = value
            event["event_digest"] = codex_pilot_audit_event_digest(event)
            event_validation = validate_codex_pilot_audit_event_record(event)
            event_binding = validate_codex_pilot_audit_event_binding(
                event,
                claim_record,
                previous_event,
            )
            if not (
                event_validation["event_structural_valid"]
                and event_binding["event_binding_passed"]
            ):
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("event_invalid")

            updated_events = [*audit_events, event]
            snapshot_result = derive_codex_pilot_attempt_snapshot(
                claim_record,
                updated_events,
            )
            updated_snapshot = snapshot_result.get("snapshot")
            if not snapshot_result["snapshot_derivation_passed"] or not isinstance(
                updated_snapshot, dict
            ):
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("event_invalid")
            snapshot_binding = validate_codex_pilot_attempt_snapshot_binding(
                updated_snapshot,
                claim_record,
                updated_events,
            )
            if not snapshot_binding["snapshot_binding_passed"]:
                connection.execute("ROLLBACK")
                return _lifecycle_append_result("event_invalid")

            event_bytes = _canonical_json_bytes(event)
            snapshot_bytes = _canonical_json_bytes(updated_snapshot)
            connection.execute(
                f"""
                INSERT INTO {_LIFECYCLE_EVENTS_TABLE} (
                    attempt_id,
                    event_sequence,
                    event_bytes
                ) VALUES (?, ?, ?)
                """,
                (
                    attempt_id,
                    event["event_sequence"],
                    sqlite3.Binary(event_bytes),
                ),
            )
            cursor = connection.execute(
                f"""
                UPDATE {_CURRENT_SNAPSHOTS_TABLE}
                SET snapshot_bytes = ?
                WHERE attempt_id = ?
                """,
                (sqlite3.Binary(snapshot_bytes), attempt_id),
            )
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError("current snapshot update failed")
            self._before_lifecycle_commit(connection)
            commit_started = True
            connection.execute("COMMIT")
        except (TypeError, ValueError):
            self._rollback_quietly(connection)
            return _lifecycle_append_result("event_invalid")
        except sqlite3.Error:
            self._rollback_quietly(connection)
            if commit_started:
                category = "claim_durability_uncertain"
            elif transaction_started:
                category = "commit_incomplete"
            else:
                category = "claim_store_unavailable"
            return _lifecycle_append_result(category)
        except Exception:
            self._rollback_quietly(connection)
            category = "commit_incomplete" if transaction_started else "claim_store_unavailable"
            return _lifecycle_append_result(category)
        finally:
            if connection is not None:
                connection.close()

        return _lifecycle_append_result(
            "appended",
            event_sequence=expected_event_sequence + 1,
            lifecycle_state=next_lifecycle_state,
        )

    def read_lifecycle_state(
        self,
        attempt_id: object,
        authorization_package: object,
    ) -> dict[str, object]:
        """Read and fully revalidate the current durable lifecycle without repair."""

        try:
            trusted_authorization = deepcopy(authorization_package)
        except Exception:
            return _lifecycle_read_result("authorization_context_invalid")
        request = validate_codex_pilot_initial_claim_read_request(
            attempt_id,
            trusted_authorization,
        )
        if not request["attempt_id_valid"]:
            return _lifecycle_read_result("attempt_id_invalid")
        if not request["authorization_context_valid"]:
            return _lifecycle_read_result("authorization_context_invalid")

        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect_read_only()
            connection.execute("BEGIN")
            lifecycle_unit = self._load_lifecycle_unit(connection, attempt_id)
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            self._rollback_quietly(connection)
            return _lifecycle_read_result("claim_store_unavailable")
        except Exception:
            self._rollback_quietly(connection)
            return _lifecycle_read_result("claim_store_unavailable")
        finally:
            if connection is not None:
                connection.close()

        if lifecycle_unit is None:
            return _lifecycle_read_result("missing_commit")
        validated = self._validated_lifecycle_unit(
            lifecycle_unit,
            attempt_id,
            trusted_authorization,
        )
        if validated is None:
            return _lifecycle_read_result("committed_unit_invalid")
        claim_record, audit_events, snapshot = validated
        return _lifecycle_read_result(
            "read_success",
            claim_record=deepcopy(claim_record),
            audit_events=deepcopy(audit_events),
            snapshot=deepcopy(snapshot),
        )

    def read_initial_claim_bundle(
        self,
        attempt_id: object,
        authorization_package: object,
    ) -> object:
        """Verify one complete committed initial claim selected by exact attempt ID."""

        try:
            trusted_authorization = deepcopy(authorization_package)
        except Exception:
            return _read_result("authorization_context_invalid")

        request = validate_codex_pilot_initial_claim_read_request(
            attempt_id,
            trusted_authorization,
        )
        if not request["attempt_id_valid"]:
            return _read_result("attempt_id_invalid")
        if not request["authorization_context_valid"]:
            return _read_result("authorization_context_invalid")

        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect_read_only()
            connection.execute("BEGIN")
            selector_row = connection.execute(
                f"""
                SELECT attempt_id
                FROM {_UNIQUENESS_TABLE}
                WHERE key_kind = 'attempt_id' AND key_value = ?
                """,
                (attempt_id,),
            ).fetchone()
            if selector_row is None:
                connection.execute("ROLLBACK")
                return classify_codex_pilot_initial_claim_read_outcome(
                    attempt_id,
                    trusted_authorization,
                    {
                        "store_available": True,
                        "durability_certain": True,
                        "commit_present": False,
                    },
                    None,
                )

            committed_attempt_id = selector_row[0]
            committed_unit = self._load_committed_unit(connection, committed_attempt_id)
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            self._rollback_quietly(connection)
            return _read_result("claim_store_unavailable")
        except Exception:
            self._rollback_quietly(connection)
            return _read_result("claim_store_unavailable")
        finally:
            if connection is not None:
                connection.close()

        return classify_codex_pilot_initial_claim_read_outcome(
            attempt_id,
            trusted_authorization,
            {
                "store_available": True,
                "durability_certain": True,
                "commit_present": True,
            },
            committed_unit,
        )

    def _initialize_database(self) -> None:
        try:
            try:
                path_stat = self._database_path.stat()
            except FileNotFoundError:
                path_exists = False
            else:
                path_exists = True
                if not stat.S_ISREG(path_stat.st_mode):
                    raise _InitializationFailure

            if path_exists:
                connection = self._connect_read_only(validate_schema=False)
                try:
                    if self._schema_matches(
                        connection,
                        _CREATE_STATEMENTS,
                        _SCHEMA_VERSION,
                    ):
                        return
                    if not self._schema_matches(
                        connection,
                        _V1_CREATE_STATEMENTS,
                        1,
                    ):
                        raise _InitializationFailure
                finally:
                    connection.close()
                self._migrate_v1_database()
                return

            file_descriptor = os.open(
                self._database_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o600,
            )
            os.close(file_descriptor)
            connection = sqlite3.connect(
                self._database_path,
                timeout=10.0,
                isolation_level=None,
            )
            try:
                if self._schema_objects(connection):
                    raise _InitializationFailure
                self._configure_durable_connection(connection, initialize=True)
                connection.execute("BEGIN IMMEDIATE")
                for statement in _CREATE_STATEMENTS.values():
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                connection.execute("COMMIT")
                self._require_exact_schema(connection)
            except Exception:
                self._rollback_quietly(connection)
                raise
            finally:
                connection.close()
        except Exception:
            raise RuntimeError("claim store initialization failed") from None

    def _connect_writable(self) -> sqlite3.Connection:
        uri = f"{self._database_path.resolve(strict=False).as_uri()}?mode=rw"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=10.0,
            isolation_level=None,
        )
        try:
            self._require_exact_schema(connection)
            self._configure_durable_connection(connection, initialize=False)
        except Exception:
            connection.close()
            raise
        return connection

    def _connect_read_only(
        self,
        *,
        validate_schema: bool = True,
    ) -> sqlite3.Connection:
        uri = f"{self._database_path.resolve(strict=False).as_uri()}?mode=ro"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=10.0,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            if validate_schema:
                self._require_exact_schema(connection)
        except Exception:
            connection.close()
            raise
        return connection

    @staticmethod
    def _configure_durable_connection(
        connection: sqlite3.Connection,
        *,
        initialize: bool,
    ) -> None:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        if initialize:
            journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        else:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        connection.execute("PRAGMA synchronous = FULL")
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        if str(journal_mode).lower() != "delete" or foreign_keys != 1 or synchronous != 2:
            raise sqlite3.OperationalError("claim store durability configuration failed")

    @staticmethod
    def _schema_objects(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
        return connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

    @classmethod
    def _require_exact_schema(cls, connection: sqlite3.Connection) -> None:
        if not cls._schema_matches(connection, _CREATE_STATEMENTS, _SCHEMA_VERSION):
            raise _InitializationFailure

    @classmethod
    def _schema_matches(
        cls,
        connection: sqlite3.Connection,
        statements: dict[str, str],
        version: int,
    ) -> bool:
        objects = cls._schema_objects(connection)
        expected_tables = frozenset(statements)
        if len(objects) != len(expected_tables):
            return False
        actual_sql: dict[str, str] = {}
        for object_type, name, sql in objects:
            if object_type != "table" or name not in expected_tables or type(sql) is not str:
                return False
            actual_sql[name] = _normalized_sql(sql)
        if set(actual_sql) != expected_tables:
            return False
        for table_name, expected_sql in statements.items():
            if actual_sql[table_name] != _normalized_sql(expected_sql):
                return False
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        return user_version == version

    def _migrate_v1_database(self) -> None:
        connection: sqlite3.Connection | None = None
        try:
            uri = f"{self._database_path.resolve(strict=False).as_uri()}?mode=rw"
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=10.0,
                isolation_level=None,
            )
            self._configure_durable_connection(connection, initialize=False)
            connection.execute("BEGIN IMMEDIATE")
            if not self._schema_matches(connection, _V1_CREATE_STATEMENTS, 1):
                raise _InitializationFailure
            for statement in _V2_EXTENSION_CREATE_STATEMENTS.values():
                connection.execute(statement)
            connection.execute(
                f"""
                INSERT INTO {_CURRENT_SNAPSHOTS_TABLE} (attempt_id, snapshot_bytes)
                SELECT attempt_id, snapshot_bytes FROM {_SNAPSHOTS_TABLE}
                """
            )
            initial_count = connection.execute(
                f"SELECT COUNT(*) FROM {_SNAPSHOTS_TABLE}"
            ).fetchone()[0]
            current_count = connection.execute(
                f"SELECT COUNT(*) FROM {_CURRENT_SNAPSHOTS_TABLE}"
            ).fetchone()[0]
            if initial_count != current_count:
                raise _InitializationFailure
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._before_migration_commit(connection)
            connection.execute("COMMIT")
            self._require_exact_schema(connection)
        except Exception:
            self._rollback_quietly(connection)
            raise RuntimeError("claim store initialization failed") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _uniqueness_exists(
        connection: sqlite3.Connection,
        key_kind: str,
        key_value: str,
    ) -> bool:
        row = connection.execute(
            f"""
            SELECT 1
            FROM {_UNIQUENESS_TABLE}
            WHERE key_kind = ? AND key_value = ?
            """,
            (key_kind, key_value),
        ).fetchone()
        return row is not None

    @staticmethod
    def _load_committed_unit(
        connection: sqlite3.Connection,
        attempt_id: object,
    ) -> object:
        claim_row = connection.execute(
            f"SELECT claim_record_bytes FROM {_CLAIMS_TABLE} WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        event_rows = connection.execute(
            f"""
            SELECT event_sequence, sequence_zero_event_bytes
            FROM {_EVENTS_TABLE}
            WHERE attempt_id = ?
            ORDER BY event_sequence
            """,
            (attempt_id,),
        ).fetchall()
        snapshot_row = connection.execute(
            f"SELECT snapshot_bytes FROM {_SNAPSHOTS_TABLE} WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        uniqueness_rows = connection.execute(
            f"""
            SELECT key_kind, key_value, attempt_id
            FROM {_UNIQUENESS_TABLE}
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchall()

        if claim_row is None or len(event_rows) != 1 or snapshot_row is None:
            return None
        event_sequence, event_bytes = event_rows[0]
        if event_sequence != 0:
            return None

        uniqueness_by_kind = {
            row[0]: (row[1], row[2])
            for row in uniqueness_rows
            if type(row[0]) is str
        }
        if len(uniqueness_rows) == 3 and set(uniqueness_by_kind) == set(_UNIQUENESS_KEYS):
            uniqueness_entries = [
                {
                    key_kind: {
                        uniqueness_by_kind[key_kind][0]: uniqueness_by_kind[key_kind][1]
                    }
                }
                for key_kind in _UNIQUENESS_KEYS
            ]
        else:
            uniqueness_entries = []

        claim_bytes = claim_row[0]
        snapshot_bytes = snapshot_row[0]
        return {
            "claim_record": _decode_json_record(claim_bytes),
            "sequence_zero_event": _decode_json_record(event_bytes),
            "snapshot": _decode_json_record(snapshot_bytes),
            "claim_record_bytes": claim_bytes,
            "sequence_zero_event_bytes": event_bytes,
            "snapshot_bytes": snapshot_bytes,
            "uniqueness_entries": uniqueness_entries,
        }

    @classmethod
    def _load_lifecycle_unit(
        cls,
        connection: sqlite3.Connection,
        attempt_id: object,
    ) -> object:
        initial_unit = cls._load_committed_unit(connection, attempt_id)
        if initial_unit is None:
            return None
        later_event_rows = connection.execute(
            f"""
            SELECT event_sequence, event_bytes
            FROM {_LIFECYCLE_EVENTS_TABLE}
            WHERE attempt_id = ?
            ORDER BY event_sequence
            """,
            (attempt_id,),
        ).fetchall()
        current_snapshot_row = connection.execute(
            f"""
            SELECT snapshot_bytes
            FROM {_CURRENT_SNAPSHOTS_TABLE}
            WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if current_snapshot_row is None:
            return None
        return {
            "initial_unit": initial_unit,
            "later_event_rows": later_event_rows,
            "current_snapshot_bytes": current_snapshot_row[0],
        }

    @staticmethod
    def _validated_lifecycle_unit(
        lifecycle_unit: object,
        attempt_id: object,
        authorization_package: object,
    ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]] | None:
        if type(lifecycle_unit) is not dict or set(lifecycle_unit) != {
            "initial_unit",
            "later_event_rows",
            "current_snapshot_bytes",
        }:
            return None
        initial_unit = lifecycle_unit["initial_unit"]
        initial_validation = validate_codex_pilot_initial_claim_committed_unit(
            initial_unit,
            attempt_id,
            authorization_package,
        )
        if not initial_validation["committed_unit_validation_passed"]:
            return None
        claim_record = initial_unit["claim_record"]
        sequence_zero_event = initial_unit["sequence_zero_event"]
        if type(claim_record) is not dict or type(sequence_zero_event) is not dict:
            return None

        audit_events: list[dict[str, object]] = [sequence_zero_event]
        later_event_rows = lifecycle_unit["later_event_rows"]
        if type(later_event_rows) is not list:
            return None
        for expected_sequence, row in enumerate(later_event_rows, start=1):
            if type(row) not in {tuple, list} or len(row) != 2:
                return None
            event_sequence, event_bytes = row
            event = _decode_json_record(event_bytes)
            if (
                event_sequence != expected_sequence
                or type(event) is not dict
                or event.get("event_sequence") != expected_sequence
                or type(event_bytes) is not bytes
                or _canonical_json_bytes(event) != event_bytes
            ):
                return None
            audit_events.append(event)

        current_snapshot_bytes = lifecycle_unit["current_snapshot_bytes"]
        current_snapshot = _decode_json_record(current_snapshot_bytes)
        if (
            type(current_snapshot) is not dict
            or type(current_snapshot_bytes) is not bytes
            or _canonical_json_bytes(current_snapshot) != current_snapshot_bytes
        ):
            return None
        snapshot_binding = validate_codex_pilot_attempt_snapshot_binding(
            current_snapshot,
            claim_record,
            audit_events,
        )
        if not snapshot_binding["snapshot_binding_passed"]:
            return None
        return claim_record, audit_events, current_snapshot

    @staticmethod
    def _rollback_quietly(connection: sqlite3.Connection | None) -> None:
        if connection is None:
            return
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _before_commit(self, connection: sqlite3.Connection) -> None:
        """Deterministic test seam immediately before the atomic commit."""

        del connection

    def _before_lifecycle_commit(self, connection: sqlite3.Connection) -> None:
        """Deterministic test seam before an event/snapshot transaction commits."""

        del connection

    def _before_migration_commit(self, connection: sqlite3.Connection) -> None:
        """Deterministic test seam before a v1-to-v2 migration commits."""

        del connection
