"""Durable local SQLite storage for supervised-Codex initial claim units."""

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
    codex_pilot_authorization_fingerprint,
    validate_codex_pilot_authorization_packet,
    validate_codex_pilot_initial_claim_read_request,
    validate_codex_pilot_initial_claim_store_create_result,
    validate_codex_pilot_initial_claim_store_read_result,
    validate_codex_pilot_prepared_initial_claim_commit,
)

_SCHEMA_VERSION: Final = 1
_CLAIMS_TABLE: Final = "codex_pilot_v1_initial_claims"
_EVENTS_TABLE: Final = "codex_pilot_v1_initial_audit_events"
_SNAPSHOTS_TABLE: Final = "codex_pilot_v1_initial_snapshots"
_UNIQUENESS_TABLE: Final = "codex_pilot_v1_initial_uniqueness"
_UNIQUENESS_KEYS: Final = (
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint",
)

_CREATE_STATEMENTS: Final = {
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
_EXPECTED_TABLES: Final = frozenset(_CREATE_STATEMENTS)


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


class SQLiteCodexPilotInitialClaimStore:
    """Atomic create/read adapter for one dedicated local claim-state database."""

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
                    self._require_exact_schema(connection)
                finally:
                    connection.close()
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
        objects = cls._schema_objects(connection)
        if len(objects) != len(_EXPECTED_TABLES):
            raise _InitializationFailure
        actual_sql: dict[str, str] = {}
        for object_type, name, sql in objects:
            if object_type != "table" or name not in _EXPECTED_TABLES or type(sql) is not str:
                raise _InitializationFailure
            actual_sql[name] = _normalized_sql(sql)
        if set(actual_sql) != _EXPECTED_TABLES:
            raise _InitializationFailure
        for table_name, expected_sql in _CREATE_STATEMENTS.items():
            if actual_sql[table_name] != _normalized_sql(expected_sql):
                raise _InitializationFailure
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if user_version != _SCHEMA_VERSION:
            raise _InitializationFailure

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
