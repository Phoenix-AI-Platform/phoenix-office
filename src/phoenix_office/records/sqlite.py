"""SQLite-backed repositories for Phoenix Office customer and job records."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from phoenix_office.models.records import CustomerRecord, JobRecord, JobStatus, TankLocationType


def initialize_records_database(db_path: Path) -> None:
    """Create the customer and job record tables if they do not exist."""
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                phone TEXT NULL,
                email TEXT NULL,
                billing_street_address TEXT NULL,
                billing_city_state_zip TEXT NULL,
                notes_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                job_name TEXT NOT NULL,
                site_street_address TEXT NOT NULL,
                site_city_state_zip TEXT NOT NULL,
                status TEXT NOT NULL,
                tank_location_type TEXT NOT NULL,
                tank_size_gallons INTEGER NULL,
                tank_contents TEXT NULL,
                contents_known INTEGER NOT NULL,
                scope_notes_json TEXT NOT NULL,
                internal_notes_json TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _require_sidecar_free_immutable_read(db_path: Path) -> None:
    sidecar_paths = [Path(f"{db_path}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    if any(path.exists() for path in sidecar_paths):
        raise sqlite3.OperationalError(
            "immutable reads require a closed SQLite database without sidecar files"
        )


class SQLiteCustomerRepository:
    """SQLite CustomerRepository implementation for local customer records."""

    def __init__(
        self,
        db_path: Path,
        *,
        initialize: bool = True,
        read_only: bool = False,
    ) -> None:
        if read_only and initialize:
            raise ValueError("read-only customer repositories cannot initialize tables")
        self.db_path = Path(db_path)
        self.read_only = read_only
        if initialize:
            initialize_records_database(self.db_path)

    def save_customer(self, record: CustomerRecord) -> CustomerRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customers (
                    customer_id,
                    display_name,
                    phone,
                    email,
                    billing_street_address,
                    billing_city_state_zip,
                    notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    phone = excluded.phone,
                    email = excluded.email,
                    billing_street_address = excluded.billing_street_address,
                    billing_city_state_zip = excluded.billing_city_state_zip,
                    notes_json = excluded.notes_json
                """,
                (
                    record.customer_id,
                    record.display_name,
                    record.phone,
                    record.email,
                    record.billing_street_address,
                    record.billing_city_state_zip,
                    json.dumps(record.notes),
                ),
            )
            connection.commit()
        return record

    def get_customer(self, customer_id: str) -> CustomerRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM customers WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        if row is None:
            return None
        return _customer_from_row(row)

    def list_customers(self) -> list[CustomerRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM customers ORDER BY rowid").fetchall()
        return [_customer_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            _require_sidecar_free_immutable_read(self.db_path)
            database_uri = (
                f"{self.db_path.resolve().as_uri()}"
                "?mode=ro&immutable=1"
            )
            connection = sqlite3.connect(database_uri, uri=True)
        else:
            connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


class SQLiteJobRepository:
    """SQLite JobRepository implementation for local job records."""

    def __init__(
        self,
        db_path: Path,
        *,
        initialize: bool = True,
        read_only: bool = False,
    ) -> None:
        if read_only and initialize:
            raise ValueError("read-only job repositories cannot initialize tables")
        self.db_path = Path(db_path)
        self.read_only = read_only
        if initialize:
            initialize_records_database(self.db_path)

    def save_job(self, record: JobRecord) -> JobRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id,
                    customer_id,
                    job_name,
                    site_street_address,
                    site_city_state_zip,
                    status,
                    tank_location_type,
                    tank_size_gallons,
                    tank_contents,
                    contents_known,
                    scope_notes_json,
                    internal_notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    job_name = excluded.job_name,
                    site_street_address = excluded.site_street_address,
                    site_city_state_zip = excluded.site_city_state_zip,
                    status = excluded.status,
                    tank_location_type = excluded.tank_location_type,
                    tank_size_gallons = excluded.tank_size_gallons,
                    tank_contents = excluded.tank_contents,
                    contents_known = excluded.contents_known,
                    scope_notes_json = excluded.scope_notes_json,
                    internal_notes_json = excluded.internal_notes_json
                """,
                (
                    record.job_id,
                    record.customer_id,
                    record.job_name,
                    record.site_street_address,
                    record.site_city_state_zip,
                    record.status.value,
                    record.tank_location_type.value,
                    record.tank_size_gallons,
                    record.tank_contents,
                    int(record.contents_known),
                    json.dumps(record.scope_notes),
                    json.dumps(record.internal_notes),
                ),
            )
            connection.commit()
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return _job_from_row(row)

    def list_jobs(self) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY rowid").fetchall()
        return [_job_from_row(row) for row in rows]

    def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE customer_id = ? ORDER BY rowid",
                (customer_id,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            _require_sidecar_free_immutable_read(self.db_path)
            database_uri = (
                f"{self.db_path.resolve().as_uri()}"
                "?mode=ro&immutable=1"
            )
            connection = sqlite3.connect(database_uri, uri=True)
        else:
            connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _customer_from_row(row: sqlite3.Row) -> CustomerRecord:
    return CustomerRecord(
        customer_id=row["customer_id"],
        display_name=row["display_name"],
        phone=row["phone"],
        email=row["email"],
        billing_street_address=row["billing_street_address"],
        billing_city_state_zip=row["billing_city_state_zip"],
        notes=_load_json_list(row["notes_json"]),
    )


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        customer_id=row["customer_id"],
        job_name=row["job_name"],
        site_street_address=row["site_street_address"],
        site_city_state_zip=row["site_city_state_zip"],
        status=JobStatus(row["status"]),
        tank_location_type=TankLocationType(row["tank_location_type"]),
        tank_size_gallons=row["tank_size_gallons"],
        tank_contents=row["tank_contents"],
        contents_known=bool(row["contents_known"]),
        scope_notes=_load_json_list(row["scope_notes_json"]),
        internal_notes=_load_json_list(row["internal_notes_json"]),
    )


def _load_json_list(value: str) -> list[Any]:
    data = json.loads(value)
    if isinstance(data, list):
        return data
    return []
