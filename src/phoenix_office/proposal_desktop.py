"""Local desktop adapter for record-backed proposal draft generation.

The module deliberately keeps toolkit loading and all GUI construction behind
``main()``. Importing it is therefore safe in headless environments and has no
filesystem, database, process, or window side effects.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from phoenix_office.models.proposal import CompanyConfig, PricingLine, ScopeItem
from phoenix_office.models.records import (
    CustomerRecord,
    JobRecord,
    JobStatus,
    TankLocationType,
)
from phoenix_office.proposal_build import (
    ProposalDraftBuildRequest,
    ProposalDraftBuildResult,
    ProposalDraftValidationResult,
    build_proposal_draft,
    validate_proposal_draft,
)
from phoenix_office.records import (
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    CustomerUpdateConflictError,
    JobAlreadyExistsError,
    JobNotFoundError,
    JobUpdateConflictError,
    RecordProposalDetails,
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    initialize_records_database,
)

CustomerRepositoryFactory = Callable[..., SQLiteCustomerRepository]
CustomerCreationRepositoryFactory = Callable[..., SQLiteCustomerRepository]
CustomerUpdateRepositoryFactory = Callable[..., SQLiteCustomerRepository]
JobRepositoryFactory = Callable[..., SQLiteJobRepository]
JobCreationRepositoryFactory = Callable[..., SQLiteJobRepository]
JobUpdateRepositoryFactory = Callable[..., SQLiteJobRepository]
ValidationFunction = Callable[[ProposalDraftBuildRequest], ProposalDraftValidationResult]
BuildFunction = Callable[[ProposalDraftBuildRequest], ProposalDraftBuildResult]
PathOpener = Callable[[Path], None]
Clock = Callable[[], datetime]
RecordsDatabaseInitializer = Callable[[Path], None]
RecordsDatabaseValidator = Callable[[Path], None]

_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

_TEXT_FIELDS = frozenset(
    {
        "database_path",
        "template_path",
        "output_root",
        "output_folder",
        "proposal_input_json_output_path",
        "proposal_docx_output_path",
        "proposal_date",
        "item_description",
        "amount",
        "pricing_note",
        "notes",
        "company_name",
        "terms_and_conditions",
        "starting_at_label",
        "total_label",
    }
)

_CUSTOMER_CREATION_FIELDS = frozenset(
    {
        "customer_id",
        "display_name",
        "phone",
        "email",
        "billing_street_address",
        "billing_city_state_zip",
        "notes",
    }
)

_CUSTOMER_EDIT_FIELDS = frozenset(
    {
        "display_name",
        "phone",
        "email",
        "billing_street_address",
        "billing_city_state_zip",
        "notes",
    }
)

_JOB_CREATION_FIELDS = frozenset(
    {
        "job_id",
        "job_name",
        "site_street_address",
        "site_city_state_zip",
        "status",
        "tank_location_type",
        "tank_size_gallons",
        "tank_contents",
        "scope_notes",
        "internal_notes",
    }
)

_JOB_EDIT_FIELDS = frozenset(
    {
        "job_name",
        "site_street_address",
        "site_city_state_zip",
        "status",
        "tank_location_type",
        "tank_size_gallons",
        "tank_contents",
        "scope_notes",
        "internal_notes",
    }
)


class DesktopFormError(ValueError):
    """A local operator-facing form state error."""


class ExistingOutputPathError(DesktopFormError):
    """The operator selected an output path that must not be overwritten."""


class NoCustomerChangesError(DesktopFormError):
    """A customer save was requested without any persisted field changes."""


class NoJobChangesError(DesktopFormError):
    """A job save was requested without any persisted field changes."""


@dataclass(frozen=True, slots=True)
class DesktopFormSnapshot:
    """Immutable representation of every input that affects a draft request."""

    database_path: str
    template_path: str
    output_root: str
    output_folder: str
    proposal_input_json_output_path: str
    proposal_docx_output_path: str
    selected_customer_id: str
    selected_job_id: str
    proposal_date: str
    item_description: str
    scope_descriptions: tuple[str, ...]
    amount: str
    is_starting_at: bool
    pricing_note: str
    notes: str
    company_name: str
    terms_and_conditions: str
    starting_at_label: str
    total_label: str


@dataclass(frozen=True, slots=True)
class _ValidatedResolvedPaths:
    """Private resolved locations associated with one successful validation."""

    records_database: Path
    docx_template: Path
    output_root: Path
    output_folder: Path
    proposal_input_json: Path
    proposal_docx: Path

    def labeled_paths(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("Records Database", self.records_database),
            ("DOCX Template", self.docx_template),
            ("Output Root", self.output_root),
            ("Output Folder", self.output_folder),
            ("Proposal Input JSON", self.proposal_input_json),
            ("Proposal DOCX", self.proposal_docx),
        )

    def first_mismatch(self, other: _ValidatedResolvedPaths) -> str | None:
        for (label, expected), (_, current) in zip(
            self.labeled_paths(),
            other.labeled_paths(),
            strict=True,
        ):
            if current != expected:
                return label
        return None


@dataclass(frozen=True, slots=True)
class _OwnedFileIdentity:
    """Stable identity for one file exclusively created by this process."""

    device: int
    inode: int


@dataclass(slots=True)
class DesktopFormState:
    """Mutable controller state containing only explicit local form values."""

    database_path: str = ""
    template_path: str = ""
    output_root: str = ""
    output_folder: str = ""
    proposal_input_json_output_path: str = "proposal_input.json"
    proposal_docx_output_path: str = "proposal.docx"
    selected_customer_id: str = ""
    selected_job_id: str = ""
    proposal_date: str = ""
    item_description: str = ""
    scope_descriptions: list[str] = field(default_factory=lambda: [""])
    amount: str = ""
    is_starting_at: bool = False
    pricing_note: str = ""
    notes: str = ""
    company_name: str = ""
    terms_and_conditions: str = ""
    starting_at_label: str = "Starting at"
    total_label: str = "TOTAL"


@dataclass(slots=True)
class CustomerCreationState:
    """Explicit operator-entered values for one create-only customer insert."""

    customer_id: str = ""
    display_name: str = ""
    phone: str = ""
    email: str = ""
    billing_street_address: str = ""
    billing_city_state_zip: str = ""
    notes: str = ""


@dataclass(slots=True)
class CustomerEditState:
    """Editable persisted values copied from one deliberately selected customer."""

    customer_id: str = ""
    display_name: str = ""
    phone: str = ""
    email: str = ""
    billing_street_address: str = ""
    billing_city_state_zip: str = ""
    notes: str = ""


@dataclass(slots=True)
class JobCreationState:
    """Explicit operator-entered values for one create-only job insert."""

    job_id: str = ""
    job_name: str = ""
    site_street_address: str = ""
    site_city_state_zip: str = ""
    status: str = JobStatus.draft.value
    tank_location_type: str = TankLocationType.unknown.value
    tank_size_gallons: str = ""
    tank_contents: str = ""
    contents_known: bool = False
    scope_notes: str = ""
    internal_notes: str = ""


@dataclass(slots=True)
class JobEditState:
    """Editable persisted values copied from one deliberately selected job."""

    job_id: str = ""
    customer_id: str = ""
    job_name: str = ""
    site_street_address: str = ""
    site_city_state_zip: str = ""
    status: str = JobStatus.draft.value
    tank_location_type: str = TankLocationType.unknown.value
    tank_size_gallons: str = ""
    tank_contents: str = ""
    contents_known: bool = False
    scope_notes: str = ""
    internal_notes: str = ""


def _load_tkinter() -> tuple[object, object, object, object]:
    """Load the standard GUI toolkit only when the desktop entrypoint runs."""

    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    return tk, ttk, filedialog, messagebox


def _clear_combobox_selection(combobox: Any, variable: Any) -> None:
    """Clear a readonly combobox without using an invalid negative index."""

    variable.set("")
    combobox.set("")


def _default_customer_repository_factory(
    database_path: Path,
    *,
    initialize: bool,
    read_only: bool,
) -> SQLiteCustomerRepository:
    return SQLiteCustomerRepository(
        database_path,
        initialize=initialize,
        read_only=read_only,
    )


def _default_job_repository_factory(
    database_path: Path,
    *,
    initialize: bool,
    read_only: bool,
) -> SQLiteJobRepository:
    return SQLiteJobRepository(
        database_path,
        initialize=initialize,
        read_only=read_only,
    )


def _default_records_database_validator(database_path: Path) -> None:
    """Read both initialized tables without mutating the new database."""

    customers = _default_customer_repository_factory(
        database_path,
        initialize=False,
        read_only=True,
    ).list_customers()
    jobs = _default_job_repository_factory(
        database_path,
        initialize=False,
        read_only=True,
    ).list_jobs()
    if customers or jobs:
        raise DesktopFormError("New records database contains unexpected records.")


def _file_identity(metadata: os.stat_result) -> _OwnedFileIdentity | None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_ino <= 0:
        return None
    return _OwnedFileIdentity(device=metadata.st_dev, inode=metadata.st_ino)


def _created_file_identity(path: Path) -> _OwnedFileIdentity | None:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError):
        return None
    return _file_identity(metadata)


def _path_is_absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _cleanup_owned_records_database(
    database_path: Path,
    expected_identity: _OwnedFileIdentity,
) -> bool:
    """Remove the claimed database only when no unowned sidecars remain."""

    if _created_file_identity(database_path) != expected_identity:
        return False

    # The initializer provides no sidecar creation receipts. Neither initial
    # absence nor a later observed identity establishes ownership of a sidecar.
    if any(
        not _path_is_absent(Path(f"{database_path}{suffix}"))
        for suffix in _SQLITE_SIDECAR_SUFFIXES
    ):
        return False
    if _created_file_identity(database_path) != expected_identity:
        return False
    try:
        database_path.unlink()
    except OSError:
        return False
    return _path_is_absent(database_path)


def _open_local_path(path: Path) -> None:
    """Hand one explicit generated local path to the operating system."""

    if os.name == "nt":
        startfile = getattr(os, "startfile")
        startfile(str(path))
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run(
        [command, str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _inspect_git_worktree_ancestry(path: Path) -> tuple[Path, bool]:
    """Resolve one selected path and inspect only its ancestor chain."""

    resolved = path.expanduser().resolve(strict=False)
    try:
        selected_metadata = resolved.stat()
    except FileNotFoundError:
        start = resolved.parent
    else:
        start = resolved if stat.S_ISDIR(selected_metadata.st_mode) else resolved.parent

    for directory in (start, *start.parents):
        marker = directory / ".git"
        try:
            marker.lstat()
        except FileNotFoundError:
            continue
        return resolved, True
    return resolved, False


def is_path_inside_git_worktree(path: Path) -> bool:
    """Check only the selected path's directory and ancestor chain for ``.git``."""

    _, inside_worktree = _inspect_git_worktree_ancestry(path)
    return inside_worktree


def propose_identity_free_output_paths(
    output_root: Path,
    *,
    clock: Clock,
) -> tuple[Path, Path, Path]:
    """Propose identity-free paths without creating any directory or file."""

    timestamp = clock().strftime("%Y%m%d-%H%M%S")
    output_folder = output_root / f"proposal-draft-{timestamp}"
    return (
        output_folder,
        output_folder / "proposal_input.json",
        output_folder / "proposal.docx",
    )


class ProposalDesktopController:
    """Headless controller for explicit existing-record proposal intake."""

    def __init__(
        self,
        *,
        validation_function: ValidationFunction = validate_proposal_draft,
        build_function: BuildFunction = build_proposal_draft,
        customer_repository_factory: CustomerRepositoryFactory = (
            _default_customer_repository_factory
        ),
        customer_creation_repository_factory: CustomerCreationRepositoryFactory = (
            _default_customer_repository_factory
        ),
        customer_update_repository_factory: CustomerUpdateRepositoryFactory = (
            _default_customer_repository_factory
        ),
        job_repository_factory: JobRepositoryFactory = _default_job_repository_factory,
        job_creation_repository_factory: JobCreationRepositoryFactory = (
            _default_job_repository_factory
        ),
        job_update_repository_factory: JobUpdateRepositoryFactory = (
            _default_job_repository_factory
        ),
        records_database_initializer: RecordsDatabaseInitializer = (
            initialize_records_database
        ),
        records_database_validator: RecordsDatabaseValidator = (
            _default_records_database_validator
        ),
        path_opener: PathOpener = _open_local_path,
        clock: Clock = datetime.now,
    ) -> None:
        self._validation_function = validation_function
        self._build_function = build_function
        self._customer_repository_factory = customer_repository_factory
        self._customer_creation_repository_factory = (
            customer_creation_repository_factory
        )
        self._customer_update_repository_factory = customer_update_repository_factory
        self._job_repository_factory = job_repository_factory
        self._job_creation_repository_factory = job_creation_repository_factory
        self._job_update_repository_factory = job_update_repository_factory
        self._records_database_initializer = records_database_initializer
        self._records_database_validator = records_database_validator
        self._path_opener = path_opener
        self._clock = clock
        self.state = DesktopFormState(proposal_date=clock().date().isoformat())
        self.customer_creation_state = CustomerCreationState()
        self.customer_edit_state = CustomerEditState()
        self.job_creation_state = JobCreationState()
        self.job_edit_state = JobEditState()
        self._customer_edit_expected_original: CustomerRecord | None = None
        self._job_edit_expected_original: JobRecord | None = None
        self._customers: tuple[CustomerRecord, ...] = ()
        self._jobs: tuple[JobRecord, ...] = ()
        self._validated_request: ProposalDraftBuildRequest | None = None
        self._validated_snapshot: DesktopFormSnapshot | None = None
        self._validated_resolved_paths: _ValidatedResolvedPaths | None = None
        self._validation_result: ProposalDraftValidationResult | None = None
        self._build_result: ProposalDraftBuildResult | None = None

    @property
    def customers(self) -> tuple[CustomerRecord, ...]:
        return self._customers

    @property
    def jobs(self) -> tuple[JobRecord, ...]:
        return self._jobs

    @property
    def customer_display_labels(self) -> tuple[str, ...]:
        return tuple(
            f"{customer.display_name} [{customer.customer_id}]"
            for customer in self._customers
        )

    @property
    def job_display_labels(self) -> tuple[str, ...]:
        return tuple(f"{job.job_name} [{job.job_id}]" for job in self._jobs)

    @property
    def validation_summary_lines(self) -> tuple[str, ...]:
        if self._validation_result is None:
            return ()
        return self._validation_result.summary_lines

    @property
    def validated_request(self) -> ProposalDraftBuildRequest | None:
        return self._validated_request

    @property
    def build_result(self) -> ProposalDraftBuildResult | None:
        return self._build_result

    @property
    def customer_edit_expected_original(self) -> CustomerRecord | None:
        return self._customer_edit_expected_original

    @property
    def job_edit_expected_original(self) -> JobRecord | None:
        return self._job_edit_expected_original

    @property
    def generation_enabled(self) -> bool:
        return (
            self._validated_request is not None
            and self._validated_snapshot is not None
            and self._validated_resolved_paths is not None
            and self._validated_snapshot == self.snapshot()
        )

    @property
    def open_actions_enabled(self) -> bool:
        return self._build_result is not None

    def snapshot(self) -> DesktopFormSnapshot:
        state = self.state
        return DesktopFormSnapshot(
            database_path=state.database_path,
            template_path=state.template_path,
            output_root=state.output_root,
            output_folder=state.output_folder,
            proposal_input_json_output_path=state.proposal_input_json_output_path,
            proposal_docx_output_path=state.proposal_docx_output_path,
            selected_customer_id=state.selected_customer_id,
            selected_job_id=state.selected_job_id,
            proposal_date=state.proposal_date,
            item_description=state.item_description,
            scope_descriptions=tuple(state.scope_descriptions),
            amount=state.amount,
            is_starting_at=state.is_starting_at,
            pricing_note=state.pricing_note,
            notes=state.notes,
            company_name=state.company_name,
            terms_and_conditions=state.terms_and_conditions,
            starting_at_label=state.starting_at_label,
            total_label=state.total_label,
        )

    def set_text_field(self, name: str, value: str) -> None:
        if name not in _TEXT_FIELDS:
            raise DesktopFormError(f"Unsupported form field: {name}")
        if getattr(self.state, name) == value:
            return
        setattr(self.state, name, value)
        if name == "database_path":
            self._customers = ()
            self._jobs = ()
            self.state.selected_customer_id = ""
            self.state.selected_job_id = ""
            self._clear_customer_edit_state()
            self._clear_job_edit_state()
        self._invalidate_validation()

    def create_records_database(self, selected_path: str | Path) -> Path:
        """Create and validate one explicit new private records database."""

        self._clear_selected_database()
        requested_path = self._required_path("New Records Database", str(selected_path))
        try:
            database_path, inside_worktree = _inspect_git_worktree_ancestry(
                requested_path
            )
        except (OSError, RuntimeError) as exc:
            raise DesktopFormError(
                "Records database ancestry could not be verified; creation was blocked."
            ) from exc
        if inside_worktree:
            raise DesktopFormError("Records Database must be outside every Git worktree.")

        self._reject_existing_output_path("Records Database", database_path)
        for suffix in _SQLITE_SIDECAR_SUFFIXES:
            self._reject_existing_output_path(
                "Records Database sidecar",
                Path(f"{database_path}{suffix}"),
            )

        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            descriptor = os.open(database_path, flags, 0o600)
        except FileExistsError as exc:
            raise ExistingOutputPathError(
                "Records Database already exists; overwrite was rejected. "
                "Choose a new filename."
            ) from exc
        except OSError as exc:
            raise DesktopFormError(
                "Records database destination could not be claimed safely."
            ) from exc
        try:
            identity = _file_identity(os.fstat(descriptor))
        finally:
            os.close(descriptor)
        if identity is None:
            raise DesktopFormError(
                "Records database destination ownership could not be verified."
            )

        try:
            self._reject_git_worktree_path("Records Database", database_path)
            self._records_database_initializer(database_path)
            self._records_database_validator(database_path)
            self._reject_git_worktree_path("Records Database", database_path)
            if _created_file_identity(database_path) != identity:
                raise DesktopFormError(
                    "Records database identity changed during initialization."
                )
        except Exception as exc:
            if not _cleanup_owned_records_database(database_path, identity):
                raise DesktopFormError(
                    "Records database creation failed and cleanup ownership could not "
                    "be verified; no database was selected."
                ) from exc
            raise DesktopFormError(
                "Records database creation failed; no database was selected."
            ) from exc

        self.state.database_path = str(database_path)
        return database_path

    def set_starting_at(self, value: bool) -> None:
        normalized = bool(value)
        if self.state.is_starting_at == normalized:
            return
        self.state.is_starting_at = normalized
        self._invalidate_validation()

    def set_customer_creation_field(self, name: str, value: str) -> None:
        if name not in _CUSTOMER_CREATION_FIELDS:
            raise DesktopFormError(f"Unsupported customer creation field: {name}")
        setattr(self.customer_creation_state, name, value)

    def create_customer_record(self) -> CustomerRecord:
        """Validate only the explicit customer values currently in the form."""

        state = self.customer_creation_state
        return CustomerRecord(
            customer_id=self._required_customer_text(
                "Customer ID",
                state.customer_id,
            ),
            display_name=self._required_customer_text(
                "Display Name",
                state.display_name,
            ),
            phone=self._optional_customer_text(state.phone),
            email=self._optional_customer_text(state.email),
            billing_street_address=self._optional_customer_text(
                state.billing_street_address
            ),
            billing_city_state_zip=self._optional_customer_text(
                state.billing_city_state_zip
            ),
            notes=[line.strip() for line in state.notes.splitlines() if line.strip()],
        )

    def create_customer(self) -> CustomerRecord:
        """Insert one explicit customer, then reload through the read-only path."""

        record = self.create_customer_record()
        database_path = self._required_path(
            "Records Database",
            self.state.database_path,
        )
        self._reject_git_worktree_path("Records Database", database_path)
        repository = self._customer_creation_repository_factory(
            database_path,
            initialize=False,
            read_only=False,
        )
        created = repository.create_customer(record)
        try:
            self.load_customers()
        except Exception as exc:
            raise DesktopFormError(
                "Customer was created, but the read-only customer reload failed."
            ) from exc
        return created

    def set_customer_edit_field(self, name: str, value: str) -> None:
        if name not in _CUSTOMER_EDIT_FIELDS:
            raise DesktopFormError(f"Unsupported customer edit field: {name}")
        setattr(self.customer_edit_state, name, value)

    def create_customer_update_record(self) -> CustomerRecord:
        """Build one update-only customer record from explicit edit values."""

        customer_id = self.state.selected_customer_id
        expected_original = self._customer_edit_expected_original
        if not customer_id or expected_original is None:
            raise DesktopFormError("Select an existing customer before saving changes.")
        if not any(customer.customer_id == customer_id for customer in self._customers):
            raise DesktopFormError(
                "The selected customer is stale or missing; reload customers."
            )
        state = self.customer_edit_state
        if (
            state.customer_id != customer_id
            or expected_original.customer_id != customer_id
        ):
            raise DesktopFormError(
                "Customer edit identity changed; reload customers before retrying."
            )
        return CustomerRecord(
            customer_id=customer_id,
            display_name=self._required_customer_update_text(
                "Display Name",
                state.display_name,
            ),
            phone=self._optional_customer_text(state.phone),
            email=self._optional_customer_text(state.email),
            billing_street_address=self._optional_customer_text(
                state.billing_street_address
            ),
            billing_city_state_zip=self._optional_customer_text(
                state.billing_city_state_zip
            ),
            job_street_address=expected_original.job_street_address,
            job_city_state_zip=expected_original.job_city_state_zip,
            notes=[line.strip() for line in state.notes.splitlines() if line.strip()],
        )

    def update_customer(self) -> CustomerRecord:
        """Guardedly update one selected customer, then reload it read-only."""

        record = self.create_customer_update_record()
        expected_original = self._customer_edit_expected_original
        if expected_original is None:  # Defensive after record construction.
            raise DesktopFormError("Select an existing customer before saving changes.")
        if self._normalized_persisted_customer_values(
            record
        ) == self._normalized_persisted_customer_values(expected_original):
            raise NoCustomerChangesError("No customer changes to save.")

        database_path = self._required_path(
            "Records Database",
            self.state.database_path,
        )
        self._reject_git_worktree_path("Records Database", database_path)
        self._invalidate_validation()
        repository = self._customer_update_repository_factory(
            database_path,
            initialize=False,
            read_only=False,
        )
        updated = repository.update_customer(record, expected_original)
        try:
            self.load_customers()
            self.select_customer(record.customer_id)
        except Exception as exc:
            raise DesktopFormError(
                "Customer was updated, but the read-only customer reload failed."
            ) from exc
        return updated

    def set_job_creation_field(self, name: str, value: str) -> None:
        if name not in _JOB_CREATION_FIELDS:
            raise DesktopFormError(f"Unsupported job creation field: {name}")
        setattr(self.job_creation_state, name, value)

    def set_job_creation_contents_known(self, value: bool) -> None:
        self.job_creation_state.contents_known = bool(value)

    def create_job_record(self) -> JobRecord:
        """Validate explicit job values for the currently selected customer."""

        customer_id = self._selected_loaded_customer_id()
        state = self.job_creation_state
        tank_size_text = state.tank_size_gallons.strip()
        try:
            tank_size = int(tank_size_text) if tank_size_text else None
        except ValueError as exc:
            raise DesktopFormError(
                "Tank Size Gallons must be a whole number."
            ) from exc

        try:
            return JobRecord(
                job_id=self._required_job_text("Job ID", state.job_id),
                customer_id=customer_id,
                job_name=self._required_job_text("Job Name", state.job_name),
                site_street_address=self._required_job_text(
                    "Site Street Address",
                    state.site_street_address,
                ),
                site_city_state_zip=self._required_job_text(
                    "Site City / State / ZIP",
                    state.site_city_state_zip,
                ),
                status=JobStatus(state.status),
                tank_location_type=TankLocationType(state.tank_location_type),
                tank_size_gallons=tank_size,
                tank_contents=self._optional_job_text(state.tank_contents),
                contents_known=state.contents_known,
                scope_notes=self._normalize_job_notes(state.scope_notes),
                internal_notes=self._normalize_job_notes(state.internal_notes),
            )
        except DesktopFormError:
            raise
        except ValueError as exc:
            raise DesktopFormError(
                "Enter valid explicit job details before creating the job."
            ) from exc

    def create_job(self) -> JobRecord:
        """Insert one explicit job, then reload selected-customer jobs read-only."""

        record = self.create_job_record()
        database_path = self._required_path(
            "Records Database",
            self.state.database_path,
        )
        self._reject_git_worktree_path("Records Database", database_path)

        customer_repository = self._customer_repository_factory(
            database_path,
            initialize=False,
            read_only=True,
        )
        current_customer = customer_repository.get_customer(record.customer_id)
        if current_customer is None:
            raise DesktopFormError(
                "The selected customer is stale or missing; reload customers."
            )

        repository = self._job_creation_repository_factory(
            database_path,
            initialize=False,
            read_only=False,
        )
        created = repository.create_job(record)
        try:
            self.select_customer(record.customer_id)
        except Exception as exc:
            raise DesktopFormError(
                "Job was created, but the read-only job reload failed."
            ) from exc
        return created

    def set_job_edit_field(self, name: str, value: str) -> None:
        if name not in _JOB_EDIT_FIELDS:
            raise DesktopFormError(f"Unsupported job edit field: {name}")
        setattr(self.job_edit_state, name, value)

    def set_job_edit_contents_known(self, value: bool) -> None:
        self.job_edit_state.contents_known = bool(value)

    def create_job_update_record(self) -> JobRecord:
        """Build one update-only job record from explicit edit values."""

        selected_customer_id = self.state.selected_customer_id
        selected_job_id = self.state.selected_job_id
        expected_original = self._job_edit_expected_original
        if not selected_customer_id or not selected_job_id or expected_original is None:
            raise DesktopFormError("Select an existing job before saving changes.")
        if not any(
            customer.customer_id == selected_customer_id
            for customer in self._customers
        ):
            raise DesktopFormError(
                "The selected customer is stale or missing; reload customers."
            )
        selected_job = next(
            (job for job in self._jobs if job.job_id == selected_job_id),
            None,
        )
        if selected_job is None or selected_job.customer_id != selected_customer_id:
            raise DesktopFormError("The selected job is stale or mismatched; reload jobs.")
        state = self.job_edit_state
        if (
            state.job_id != selected_job_id
            or state.customer_id != selected_customer_id
            or expected_original.job_id != selected_job_id
            or expected_original.customer_id != selected_customer_id
        ):
            raise DesktopFormError(
                "Job edit identity changed; reload jobs before retrying."
            )

        tank_size_text = state.tank_size_gallons.strip()
        try:
            tank_size = int(tank_size_text) if tank_size_text else None
        except ValueError as exc:
            raise DesktopFormError(
                "Tank Size Gallons must be a whole number."
            ) from exc

        try:
            return JobRecord(
                job_id=expected_original.job_id,
                customer_id=expected_original.customer_id,
                job_name=self._required_job_update_text("Job Name", state.job_name),
                site_street_address=self._required_job_update_text(
                    "Site Street Address",
                    state.site_street_address,
                ),
                site_city_state_zip=self._required_job_update_text(
                    "Site City / State / ZIP",
                    state.site_city_state_zip,
                ),
                status=JobStatus(state.status),
                tank_location_type=TankLocationType(state.tank_location_type),
                tank_size_gallons=tank_size,
                tank_contents=self._optional_job_text(state.tank_contents),
                contents_known=state.contents_known,
                scope_notes=self._normalize_job_notes(state.scope_notes),
                internal_notes=self._normalize_job_notes(state.internal_notes),
            )
        except DesktopFormError:
            raise
        except ValueError as exc:
            raise DesktopFormError(
                "Enter valid explicit job details before saving changes."
            ) from exc

    def update_job(self) -> JobRecord:
        """Guardedly update one selected job, then reload and reselect it read-only."""

        record = self.create_job_update_record()
        expected_original = self._job_edit_expected_original
        if expected_original is None:  # Defensive after record construction.
            raise DesktopFormError("Select an existing job before saving changes.")
        if self._normalized_persisted_job_values(
            record
        ) == self._normalized_persisted_job_values(expected_original):
            raise NoJobChangesError("No job changes to save.")

        database_path = self._required_path(
            "Records Database",
            self.state.database_path,
        )
        self._reject_git_worktree_path("Records Database", database_path)
        self._invalidate_validation()

        customer_repository = self._customer_repository_factory(
            database_path,
            initialize=False,
            read_only=True,
        )
        current_customer = customer_repository.get_customer(record.customer_id)
        if current_customer is None:
            raise DesktopFormError(
                "The selected customer is stale or missing; reload customers."
            )

        repository = self._job_update_repository_factory(
            database_path,
            initialize=False,
            read_only=False,
        )
        updated = repository.update_job(record, expected_original)
        try:
            self.select_customer(record.customer_id)
            self.select_job(record.job_id)
        except Exception as exc:
            raise DesktopFormError(
                "Job was updated, but the read-only job reload failed."
            ) from exc
        return updated

    def propose_output_paths(self, output_root: str | Path) -> tuple[Path, Path, Path]:
        root = Path(output_root).expanduser()
        output_folder, output_json, output_docx = propose_identity_free_output_paths(
            root,
            clock=self._clock,
        )
        self.state.output_root = str(root)
        self.state.output_folder = str(output_folder)
        self.state.proposal_input_json_output_path = str(output_json)
        self.state.proposal_docx_output_path = str(output_docx)
        self._invalidate_validation()
        return output_folder, output_json, output_docx

    def select_docx_output_path(
        self,
        selected_path: str | Path,
    ) -> tuple[Path, Path, Path]:
        """Select one explicit DOCX target without creating or replacing files."""

        selected_text = str(selected_path)
        if not selected_text.strip():
            raise DesktopFormError("Select a proposal DOCX output path.")
        output_docx = Path(selected_text).expanduser()
        if not output_docx.suffix:
            output_docx = output_docx.with_suffix(".docx")
        elif output_docx.suffix.lower() != ".docx":
            raise DesktopFormError("Proposal DOCX output must use the .docx extension.")

        output_folder = output_docx.parent
        output_json = output_folder / "proposal_input.json"
        self._reject_git_worktree_path("Proposal DOCX", output_docx)
        self._reject_git_worktree_path("Proposal Input JSON", output_json)
        self._reject_existing_output_path("Proposal DOCX", output_docx)
        self._reject_existing_output_path("Proposal Input JSON", output_json)

        self.state.output_root = str(output_folder)
        self.state.output_folder = str(output_folder)
        self.state.proposal_input_json_output_path = str(output_json)
        self.state.proposal_docx_output_path = str(output_docx)
        self._invalidate_validation()
        return output_folder, output_json, output_docx

    def load_customers(self) -> tuple[CustomerRecord, ...]:
        self._customers = ()
        self._jobs = ()
        self.state.selected_customer_id = ""
        self.state.selected_job_id = ""
        self._clear_customer_edit_state()
        self._clear_job_edit_state()
        self._invalidate_validation()
        database_path = self._required_path("Records Database", self.state.database_path)
        self._reject_git_worktree_path("Records Database", database_path)
        repository = self._customer_repository_factory(
            database_path,
            initialize=False,
            read_only=True,
        )
        customers = tuple(repository.list_customers())
        self._customers = customers
        return customers

    def select_customer(self, customer_id: str) -> tuple[JobRecord, ...]:
        self.state.selected_customer_id = ""
        self.state.selected_job_id = ""
        self._jobs = ()
        self._clear_customer_edit_state()
        self._clear_job_edit_state()
        self._invalidate_validation()
        if not customer_id:
            return ()
        selected_customer = next(
            (
                customer
                for customer in self._customers
                if customer.customer_id == customer_id
            ),
            None,
        )
        if selected_customer is None:
            raise DesktopFormError("Select an existing customer loaded from the database.")

        database_path = self._required_path("Records Database", self.state.database_path)
        self._reject_git_worktree_path("Records Database", database_path)
        repository = self._job_repository_factory(
            database_path,
            initialize=False,
            read_only=True,
        )
        jobs = tuple(repository.list_jobs_for_customer(customer_id))
        if any(job.customer_id != customer_id for job in jobs):
            raise DesktopFormError("Loaded job does not belong to the selected customer.")

        self.state.selected_customer_id = customer_id
        self._jobs = jobs
        self._populate_customer_edit_state(selected_customer)
        return jobs

    def select_job(self, job_id: str) -> None:
        self.state.selected_job_id = ""
        self._clear_job_edit_state()
        self._invalidate_validation()
        if not job_id:
            return
        selected_job = next((job for job in self._jobs if job.job_id == job_id), None)
        if selected_job is None:
            raise DesktopFormError("Select an existing job loaded for the customer.")
        if selected_job.customer_id != self.state.selected_customer_id:
            raise DesktopFormError("Selected job does not belong to the selected customer.")
        self.state.selected_job_id = job_id
        self._populate_job_edit_state(selected_job)

    def set_scope_description(self, index: int, description: str) -> None:
        self._require_scope_index(index)
        if self.state.scope_descriptions[index] == description:
            return
        self.state.scope_descriptions[index] = description
        self._invalidate_validation()

    def add_scope_item(self, description: str = "") -> int:
        self.state.scope_descriptions.append(description)
        self._invalidate_validation()
        return len(self.state.scope_descriptions) - 1

    def remove_scope_item(self, index: int) -> None:
        self._require_scope_index(index)
        del self.state.scope_descriptions[index]
        self._invalidate_validation()

    def move_scope_item(self, index: int, offset: int) -> int:
        self._require_scope_index(index)
        destination = index + offset
        if destination < 0 or destination >= len(self.state.scope_descriptions):
            return index
        descriptions = self.state.scope_descriptions
        descriptions[index], descriptions[destination] = (
            descriptions[destination],
            descriptions[index],
        )
        self._invalidate_validation()
        return destination

    def numbered_scope_items(self) -> tuple[tuple[int, str], ...]:
        return tuple(enumerate(self.state.scope_descriptions, start=1))

    def create_details(self) -> RecordProposalDetails:
        state = self.state
        item_description = self._required_text(
            "Item Description",
            state.item_description,
        )
        scope_items = [
            ScopeItem(number=index, description=description)
            for index, description in self.numbered_scope_items()
            if description.strip()
        ]
        if not scope_items:
            raise DesktopFormError("At least one non-empty scope item is required.")
        if len(scope_items) != len(state.scope_descriptions):
            raise DesktopFormError("Remove or complete every blank scope item.")

        amount_text = self._required_text("Pricing Amount", state.amount)
        pricing_note = state.pricing_note if state.pricing_note.strip() else None
        terms = (
            state.terms_and_conditions
            if state.terms_and_conditions.strip()
            else None
        )
        notes = [line for line in state.notes.splitlines() if line.strip()]

        try:
            proposal_date = date.fromisoformat(state.proposal_date)
            amount = Decimal(amount_text)
        except (ValueError, ArithmeticError) as exc:
            raise DesktopFormError("Enter a valid ISO proposal date and decimal amount.") from exc
        if not amount.is_finite():
            raise DesktopFormError("Pricing Amount must be a finite decimal value.")

        return RecordProposalDetails(
            proposal_date=proposal_date,
            item_description=item_description,
            scope_items=scope_items,
            pricing=PricingLine(
                amount=amount,
                is_starting_at=state.is_starting_at,
                pricing_note=pricing_note,
            ),
            notes=notes,
            company_config=CompanyConfig(
                company_name=self._required_text("Company Name", state.company_name),
                terms_and_conditions=terms,
                starting_at_label=self._required_text(
                    "Starting At Label",
                    state.starting_at_label,
                ),
                total_label=self._required_text("Total Label", state.total_label),
            ),
        )

    def create_request(self) -> ProposalDraftBuildRequest:
        selected_customer = next(
            (
                customer
                for customer in self._customers
                if customer.customer_id == self.state.selected_customer_id
            ),
            None,
        )
        if selected_customer is None:
            raise DesktopFormError("Select an existing customer explicitly.")
        selected_job = next(
            (job for job in self._jobs if job.job_id == self.state.selected_job_id),
            None,
        )
        if selected_job is None:
            raise DesktopFormError("Select an existing job explicitly.")
        if selected_job.customer_id != selected_customer.customer_id:
            raise DesktopFormError("Selected job does not belong to the selected customer.")

        paths = self._selected_paths()

        return ProposalDraftBuildRequest(
            customer_id=selected_customer.customer_id,
            job_id=selected_job.job_id,
            details=self.create_details(),
            database_path=paths["Records Database"],
            template_path=paths["DOCX Template"],
            proposal_input_json_output_path=paths["Proposal Input JSON"],
            proposal_docx_output_path=paths["Proposal DOCX"],
        )

    def validate_draft(self) -> ProposalDraftValidationResult:
        self._invalidate_validation()
        snapshot = self.snapshot()
        request = self.create_request()
        resolved_paths_before = self._resolve_and_check_selected_paths()
        self._require_outputs_inside_resolved_folder(resolved_paths_before)
        result = self._validation_function(request)
        resolved_paths_after = self._resolve_and_check_selected_paths()
        mismatch = resolved_paths_before.first_mismatch(resolved_paths_after)
        if mismatch is not None:
            raise DesktopFormError(
                f"{mismatch} resolved location changed; revalidation is required."
            )
        self._validated_request = request
        self._validated_snapshot = snapshot
        self._validated_resolved_paths = resolved_paths_after
        self._validation_result = result
        return result

    def generate_draft(self) -> ProposalDraftBuildResult:
        self._build_result = None
        request = self._validated_request
        snapshot = self._validated_snapshot
        resolved_paths = self._validated_resolved_paths
        if request is None or snapshot is None or resolved_paths is None:
            raise DesktopFormError("Validate the current draft before generation.")
        if snapshot != self.snapshot():
            self._invalidate_validation()
            raise DesktopFormError("Draft inputs changed; revalidate before generation.")
        try:
            current_resolved_paths = self._resolve_and_check_selected_paths()
        except DesktopFormError:
            self._invalidate_validation()
            raise
        mismatch = resolved_paths.first_mismatch(current_resolved_paths)
        if mismatch is not None:
            self._invalidate_validation()
            raise DesktopFormError(
                f"{mismatch} resolved location changed; revalidation is required."
            )
        result = self._build_function(request)
        self._build_result = result
        return result

    def open_proposal_input_json(self) -> None:
        result = self._require_build_result()
        self._path_opener(result.proposal_input_json_path)

    def open_proposal_docx(self) -> None:
        result = self._require_build_result()
        self._path_opener(result.proposal_docx_path)

    def open_output_folder(self) -> None:
        result = self._require_build_result()
        self._path_opener(result.proposal_input_json_path.parent)

    def _selected_paths(self) -> dict[str, Path]:
        state = self.state
        return {
            "Records Database": self._required_path(
                "Records Database",
                state.database_path,
            ),
            "DOCX Template": self._required_path("DOCX Template", state.template_path),
            "Output Root": self._required_path("Output Root", state.output_root),
            "Output Folder": self._required_path("Output Folder", state.output_folder),
            "Proposal Input JSON": self._required_path(
                "Proposal Input JSON",
                state.proposal_input_json_output_path,
            ),
            "Proposal DOCX": self._required_path(
                "Proposal DOCX",
                state.proposal_docx_output_path,
            ),
        }

    @staticmethod
    def _required_text(label: str, value: str) -> str:
        if not value.strip():
            raise DesktopFormError(f"{label} is required.")
        return value

    @staticmethod
    def _required_customer_text(label: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise DesktopFormError(f"{label} is required before creating a customer.")
        return normalized

    @staticmethod
    def _required_customer_update_text(label: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise DesktopFormError(f"{label} is required before saving customer changes.")
        return normalized

    @staticmethod
    def _optional_customer_text(value: str) -> str | None:
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalized_persisted_customer_values(
        record: CustomerRecord,
    ) -> tuple[Any, ...]:
        def optional(value: str | None) -> str | None:
            return value.strip() or None if value is not None else None

        return (
            record.customer_id,
            record.display_name.strip(),
            optional(record.phone),
            optional(record.email),
            optional(record.billing_street_address),
            optional(record.billing_city_state_zip),
            tuple(line.strip() for line in record.notes if line.strip()),
        )

    def _clear_customer_edit_state(self) -> None:
        self.customer_edit_state = CustomerEditState()
        self._customer_edit_expected_original = None

    def _clear_selected_database(self) -> None:
        self.state.database_path = ""
        self._customers = ()
        self._jobs = ()
        self.state.selected_customer_id = ""
        self.state.selected_job_id = ""
        self._clear_customer_edit_state()
        self._clear_job_edit_state()
        self._invalidate_validation()

    def _populate_customer_edit_state(self, customer: CustomerRecord) -> None:
        self.customer_edit_state = CustomerEditState(
            customer_id=customer.customer_id,
            display_name=customer.display_name,
            phone=customer.phone or "",
            email=customer.email or "",
            billing_street_address=customer.billing_street_address or "",
            billing_city_state_zip=customer.billing_city_state_zip or "",
            notes="\n".join(customer.notes),
        )
        self._customer_edit_expected_original = customer

    def _clear_job_edit_state(self) -> None:
        self.job_edit_state = JobEditState()
        self._job_edit_expected_original = None

    def _populate_job_edit_state(self, job: JobRecord) -> None:
        self.job_edit_state = JobEditState(
            job_id=job.job_id,
            customer_id=job.customer_id,
            job_name=job.job_name,
            site_street_address=job.site_street_address,
            site_city_state_zip=job.site_city_state_zip,
            status=job.status.value,
            tank_location_type=job.tank_location_type.value,
            tank_size_gallons=(
                str(job.tank_size_gallons)
                if job.tank_size_gallons is not None
                else ""
            ),
            tank_contents=job.tank_contents or "",
            contents_known=job.contents_known,
            scope_notes="\n".join(job.scope_notes),
            internal_notes="\n".join(job.internal_notes),
        )
        self._job_edit_expected_original = job

    def _selected_loaded_customer_id(self) -> str:
        customer_id = self.state.selected_customer_id
        if not customer_id:
            raise DesktopFormError("Select an existing customer before creating a job.")
        if not any(customer.customer_id == customer_id for customer in self._customers):
            raise DesktopFormError(
                "The selected customer is stale or missing; reload customers."
            )
        return customer_id

    @staticmethod
    def _required_job_text(label: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise DesktopFormError(f"{label} is required to create a job.")
        return normalized

    @staticmethod
    def _required_job_update_text(label: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise DesktopFormError(f"{label} is required before saving job changes.")
        return normalized

    @staticmethod
    def _optional_job_text(value: str) -> str | None:
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_job_notes(value: str) -> list[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]

    @staticmethod
    def _normalized_persisted_job_values(record: JobRecord) -> tuple[Any, ...]:
        tank_contents = (
            record.tank_contents.strip() or None
            if record.tank_contents is not None
            else None
        )
        return (
            record.job_id,
            record.customer_id,
            record.job_name.strip(),
            record.site_street_address.strip(),
            record.site_city_state_zip.strip(),
            record.status,
            record.tank_location_type,
            record.tank_size_gallons,
            tank_contents,
            record.contents_known,
            tuple(line.strip() for line in record.scope_notes if line.strip()),
            tuple(line.strip() for line in record.internal_notes if line.strip()),
        )

    @staticmethod
    def _required_path(label: str, value: str) -> Path:
        if not value.strip():
            raise DesktopFormError(f"{label} is required.")
        return Path(value).expanduser()

    @staticmethod
    def _reject_git_worktree_path(label: str, path: Path) -> None:
        try:
            _, inside_worktree = _inspect_git_worktree_ancestry(path)
        except (OSError, RuntimeError) as exc:
            raise DesktopFormError(
                f"{label} ancestry could not be verified; revalidation is required."
            ) from exc
        if inside_worktree:
            raise DesktopFormError(f"{label} must be outside every Git worktree.")

    @staticmethod
    def _reject_existing_output_path(label: str, path: Path) -> None:
        try:
            path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise DesktopFormError(f"{label} could not be inspected safely.") from exc
        raise ExistingOutputPathError(
            f"{label} already exists; overwrite was rejected. Choose a new filename."
        )

    def _resolve_and_check_selected_paths(self) -> _ValidatedResolvedPaths:
        resolved: dict[str, Path] = {}
        for label, path in self._selected_paths().items():
            try:
                resolved_path, inside_worktree = _inspect_git_worktree_ancestry(path)
            except (OSError, RuntimeError) as exc:
                raise DesktopFormError(
                    f"{label} ancestry could not be verified; revalidation is required."
                ) from exc
            if inside_worktree:
                raise DesktopFormError(f"{label} must be outside every Git worktree.")
            resolved[label] = resolved_path
        return _ValidatedResolvedPaths(
            records_database=resolved["Records Database"],
            docx_template=resolved["DOCX Template"],
            output_root=resolved["Output Root"],
            output_folder=resolved["Output Folder"],
            proposal_input_json=resolved["Proposal Input JSON"],
            proposal_docx=resolved["Proposal DOCX"],
        )

    @staticmethod
    def _require_outputs_inside_resolved_folder(
        resolved_paths: _ValidatedResolvedPaths,
    ) -> None:
        if resolved_paths.proposal_input_json.parent != resolved_paths.output_folder:
            raise DesktopFormError("Proposal Input JSON must be inside the output folder.")
        if resolved_paths.proposal_docx.parent != resolved_paths.output_folder:
            raise DesktopFormError("Proposal DOCX must be inside the output folder.")

    def _require_scope_index(self, index: int) -> None:
        if index < 0 or index >= len(self.state.scope_descriptions):
            raise DesktopFormError("Select a valid scope item.")

    def _require_build_result(self) -> ProposalDraftBuildResult:
        if self._build_result is None:
            raise DesktopFormError("Generate the proposal draft before opening artifacts.")
        return self._build_result

    def _invalidate_validation(self) -> None:
        self._validated_request = None
        self._validated_snapshot = None
        self._validated_resolved_paths = None
        self._validation_result = None
        self._build_result = None


class ProposalDesktopApp:
    """Straightforward Tk widget adapter over :class:`ProposalDesktopController`."""

    def __init__(
        self,
        root: object,
        *,
        controller: ProposalDesktopController | None = None,
        toolkit: tuple[object, object, object, object] | None = None,
    ) -> None:
        self.controller = controller or ProposalDesktopController()
        self._tk, self._ttk, self._filedialog, self._messagebox = (
            toolkit or _load_tkinter()
        )
        self._root = root
        self._updating_widgets = False
        self._variables: dict[str, Any] = {}
        self._customer_creation_variables: dict[str, Any] = {}
        self._customer_edit_variables: dict[str, Any] = {}
        self._job_creation_variables: dict[str, Any] = {}
        self._job_edit_variables: dict[str, Any] = {}
        self._build_widgets()
        self._bind_state_changes()
        self._refresh_scope_list(0)
        self._refresh_action_states()

    def _build_widgets(self) -> None:
        tk = self._tk
        ttk = self._ttk
        root = self._root
        root.title("Phoenix Office Proposal Draft")
        root.minsize(900, 700)

        container = ttk.Frame(root)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self._form = ttk.Frame(canvas, padding=12)
        window = canvas.create_window((0, 0), window=self._form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._form.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )

        self._build_workspace_section()
        self._build_customer_creation_section()
        self._build_customer_edit_section()
        self._build_job_section()
        self._build_job_creation_section()
        self._build_job_edit_section()
        self._build_details_section()
        self._build_actions_section()

    def _section(self, title: str, row: int) -> object:
        frame = self._ttk.LabelFrame(self._form, text=title, padding=10)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        self._form.columnconfigure(0, weight=1)
        return frame

    def _string_variable(self, name: str, value: str) -> object:
        variable = self._tk.StringVar(value=value)
        self._variables[name] = variable
        return variable

    def _customer_creation_string_variable(self, name: str, value: str) -> object:
        variable = self._tk.StringVar(value=value)
        self._customer_creation_variables[name] = variable
        return variable

    def _customer_edit_string_variable(self, name: str, value: str) -> object:
        variable = self._tk.StringVar(value=value)
        self._customer_edit_variables[name] = variable
        return variable

    def _job_creation_string_variable(self, name: str, value: str) -> object:
        variable = self._tk.StringVar(value=value)
        self._job_creation_variables[name] = variable
        return variable

    def _job_edit_string_variable(self, name: str, value: str) -> object:
        variable = self._tk.StringVar(value=value)
        self._job_edit_variables[name] = variable
        return variable

    def _labeled_entry(
        self,
        parent: object,
        *,
        row: int,
        label: str,
        name: str,
        value: str,
        browse_command: Callable[[], None] | None = None,
    ) -> object:
        self._ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=3,
        )
        variable = self._string_variable(name, value)
        entry = self._ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        if browse_command is not None:
            self._ttk.Button(parent, text="Browse", command=browse_command).grid(
                row=row,
                column=2,
                padx=(8, 0),
                pady=3,
            )
        return entry

    def _build_workspace_section(self) -> None:
        state = self.controller.state
        frame = self._section("Step 1 — Private Workspace and Existing Customer", 0)
        self._labeled_entry(
            frame,
            row=0,
            label="Records Database",
            name="database_path",
            value=state.database_path,
            browse_command=self._browse_database,
        )
        self._ttk.Button(
            frame,
            text="Create New Records Database",
            command=self._create_records_database,
        ).grid(row=0, column=3, padx=(8, 0), pady=3)
        self._labeled_entry(
            frame,
            row=1,
            label="DOCX Template",
            name="template_path",
            value=state.template_path,
            browse_command=self._browse_template,
        )
        self._labeled_entry(
            frame,
            row=2,
            label="Output Root",
            name="output_root",
            value=state.output_root,
            browse_command=self._browse_output_root,
        )
        self._ttk.Label(frame, text="Existing Customer").grid(
            row=3,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=3,
        )
        self._customer_variable = self._tk.StringVar(value="")
        self._customer_combo = self._ttk.Combobox(
            frame,
            textvariable=self._customer_variable,
            state="readonly",
        )
        self._customer_combo.grid(row=3, column=1, sticky="ew", pady=3)
        self._customer_combo.bind("<<ComboboxSelected>>", self._on_customer_selected)
        self._ttk.Button(
            frame,
            text="Load Customers",
            command=self._load_customers,
        ).grid(row=3, column=2, padx=(8, 0), pady=3)

    def _build_customer_creation_section(self) -> None:
        state = self.controller.customer_creation_state
        frame = self._section("Create Customer — Explicit Local Insert", 1)
        for row, (label, name, value) in enumerate(
            (
                ("Customer ID", "customer_id", state.customer_id),
                ("Display Name", "display_name", state.display_name),
                ("Phone", "phone", state.phone),
                ("Email", "email", state.email),
                (
                    "Billing Street Address",
                    "billing_street_address",
                    state.billing_street_address,
                ),
                (
                    "Billing City / State / ZIP",
                    "billing_city_state_zip",
                    state.billing_city_state_zip,
                ),
            )
        ):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._customer_creation_string_variable(name, value)
            self._ttk.Entry(frame, textvariable=variable).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=3,
            )

        notes_row = len(self._customer_creation_variables)
        self._ttk.Label(frame, text="Customer Notes").grid(
            row=notes_row,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )
        self._customer_creation_notes_text = self._tk.Text(
            frame,
            height=4,
            wrap="word",
        )
        self._customer_creation_notes_text.grid(
            row=notes_row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=3,
        )
        self._customer_creation_notes_text.edit_modified(False)

        action_row = notes_row + 1
        self._ttk.Button(
            frame,
            text="Create Customer",
            command=self._create_customer,
        ).grid(row=action_row, column=1, sticky="w", pady=(6, 3))
        self._customer_creation_status_variable = self._tk.StringVar(
            value="No customer creation requested."
        )
        self._ttk.Label(
            frame,
            textvariable=self._customer_creation_status_variable,
            wraplength=760,
        ).grid(
            row=action_row + 1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(3, 0),
        )

    def _build_customer_edit_section(self) -> None:
        state = self.controller.customer_edit_state
        frame = self._section("Edit Customer — Guarded Existing-Record Update", 2)
        fields = (
            ("Customer ID", "customer_id", state.customer_id),
            ("Display Name", "display_name", state.display_name),
            ("Phone", "phone", state.phone),
            ("Email", "email", state.email),
            (
                "Billing Street Address",
                "billing_street_address",
                state.billing_street_address,
            ),
            (
                "Billing City / State / ZIP",
                "billing_city_state_zip",
                state.billing_city_state_zip,
            ),
        )
        for row, (label, name, value) in enumerate(fields):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._customer_edit_string_variable(name, value)
            self._ttk.Entry(
                frame,
                textvariable=variable,
                state="readonly" if name == "customer_id" else "normal",
            ).grid(row=row, column=1, sticky="ew", pady=3)

        notes_row = len(fields)
        self._ttk.Label(frame, text="Customer Notes").grid(
            row=notes_row,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )
        self._customer_edit_notes_text = self._tk.Text(
            frame,
            height=4,
            wrap="word",
        )
        self._customer_edit_notes_text.grid(
            row=notes_row,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=3,
        )
        self._customer_edit_notes_text.edit_modified(False)
        self._ttk.Button(
            frame,
            text="Save Customer Changes",
            command=self._update_customer,
        ).grid(row=notes_row + 1, column=1, sticky="w", pady=(6, 3))
        self._customer_edit_status_variable = self._tk.StringVar(
            value="Select an existing customer to edit."
        )
        self._ttk.Label(
            frame,
            textvariable=self._customer_edit_status_variable,
            wraplength=760,
        ).grid(
            row=notes_row + 2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(3, 0),
        )

    def _build_job_section(self) -> None:
        frame = self._section("Step 2 — Existing Job", 3)
        self._ttk.Label(frame, text="Existing Job").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=3,
        )
        self._job_variable = self._tk.StringVar(value="")
        self._job_combo = self._ttk.Combobox(
            frame,
            textvariable=self._job_variable,
            state="readonly",
        )
        self._job_combo.grid(row=0, column=1, sticky="ew", pady=3)
        self._job_combo.bind("<<ComboboxSelected>>", self._on_job_selected)

    def _build_job_creation_section(self) -> None:
        state = self.controller.job_creation_state
        frame = self._section("Create Job — Explicit Local Insert", 4)
        fields = (
            ("Job ID", "job_id", state.job_id),
            ("Job Name", "job_name", state.job_name),
            ("Site Street Address", "site_street_address", state.site_street_address),
            (
                "Site City / State / ZIP",
                "site_city_state_zip",
                state.site_city_state_zip,
            ),
            ("Tank Size Gallons", "tank_size_gallons", state.tank_size_gallons),
            ("Tank Contents", "tank_contents", state.tank_contents),
        )
        for row, (label, name, value) in enumerate(fields):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._job_creation_string_variable(name, value)
            self._ttk.Entry(frame, textvariable=variable).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=3,
            )

        row = len(fields)
        for label, name, value, choices in (
            ("Status", "status", state.status, tuple(status.value for status in JobStatus)),
            (
                "Tank Location",
                "tank_location_type",
                state.tank_location_type,
                tuple(location.value for location in TankLocationType),
            ),
        ):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._job_creation_string_variable(name, value)
            self._ttk.Combobox(
                frame,
                textvariable=variable,
                values=choices,
                state="readonly",
            ).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        self._job_creation_contents_known_variable = self._tk.BooleanVar(
            value=state.contents_known
        )
        self._ttk.Checkbutton(
            frame,
            text="Tank contents known",
            variable=self._job_creation_contents_known_variable,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        self._job_creation_scope_notes_text = self._multiline_field(
            frame,
            row,
            "Scope Notes",
            state.scope_notes,
        )
        row += 1
        self._job_creation_internal_notes_text = self._multiline_field(
            frame,
            row,
            "Internal Notes",
            state.internal_notes,
        )
        row += 1

        self._ttk.Button(
            frame,
            text="Create Job",
            command=self._create_job,
        ).grid(row=row, column=1, sticky="w", pady=(6, 3))
        self._job_creation_status_variable = self._tk.StringVar(
            value="No job creation requested."
        )
        self._ttk.Label(
            frame,
            textvariable=self._job_creation_status_variable,
            wraplength=760,
        ).grid(
            row=row + 1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(3, 0),
        )

    def _build_job_edit_section(self) -> None:
        state = self.controller.job_edit_state
        frame = self._section("Edit Job — Guarded Existing-Record Update", 5)
        fields = (
            ("Job ID", "job_id", state.job_id),
            ("Customer ID", "customer_id", state.customer_id),
            ("Job Name", "job_name", state.job_name),
            ("Site Street Address", "site_street_address", state.site_street_address),
            (
                "Site City / State / ZIP",
                "site_city_state_zip",
                state.site_city_state_zip,
            ),
            ("Tank Size Gallons", "tank_size_gallons", state.tank_size_gallons),
            ("Tank Contents", "tank_contents", state.tank_contents),
        )
        for row, (label, name, value) in enumerate(fields):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._job_edit_string_variable(name, value)
            self._ttk.Entry(
                frame,
                textvariable=variable,
                state="readonly" if name in {"job_id", "customer_id"} else "normal",
            ).grid(row=row, column=1, sticky="ew", pady=3)

        row = len(fields)
        for label, name, value, choices in (
            ("Status", "status", state.status, tuple(status.value for status in JobStatus)),
            (
                "Tank Location",
                "tank_location_type",
                state.tank_location_type,
                tuple(location.value for location in TankLocationType),
            ),
        ):
            self._ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            variable = self._job_edit_string_variable(name, value)
            self._ttk.Combobox(
                frame,
                textvariable=variable,
                values=choices,
                state="readonly",
            ).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        self._job_edit_contents_known_variable = self._tk.BooleanVar(
            value=state.contents_known
        )
        self._ttk.Checkbutton(
            frame,
            text="Tank contents known",
            variable=self._job_edit_contents_known_variable,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        self._job_edit_scope_notes_text = self._multiline_field(
            frame,
            row,
            "Scope Notes",
            state.scope_notes,
        )
        row += 1
        self._job_edit_internal_notes_text = self._multiline_field(
            frame,
            row,
            "Internal Notes",
            state.internal_notes,
        )
        row += 1

        self._ttk.Button(
            frame,
            text="Save Job Changes",
            command=self._update_job,
        ).grid(row=row, column=1, sticky="w", pady=(6, 3))
        self._job_edit_status_variable = self._tk.StringVar(
            value="Select an existing job to edit."
        )
        self._ttk.Label(
            frame,
            textvariable=self._job_edit_status_variable,
            wraplength=760,
        ).grid(
            row=row + 1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(3, 0),
        )

    def _build_details_section(self) -> None:
        state = self.controller.state
        frame = self._section("Step 3 — Explicit Proposal Details", 6)
        row = 0
        for label, name, value, browse_command in (
            ("Proposal Date", "proposal_date", state.proposal_date, None),
            ("Item Description", "item_description", state.item_description, None),
            ("Pricing Amount", "amount", state.amount, None),
            ("Pricing Note", "pricing_note", state.pricing_note, None),
            ("Company Name", "company_name", state.company_name, None),
            (
                "Starting At Label",
                "starting_at_label",
                state.starting_at_label,
                None,
            ),
            ("Total Label", "total_label", state.total_label, None),
            ("Output Folder", "output_folder", state.output_folder, None),
            (
                "Proposal Input JSON",
                "proposal_input_json_output_path",
                state.proposal_input_json_output_path,
                None,
            ),
            (
                "Proposal DOCX",
                "proposal_docx_output_path",
                state.proposal_docx_output_path,
                self._browse_docx_output,
            ),
        ):
            self._labeled_entry(
                frame,
                row=row,
                label=label,
                name=name,
                value=value,
                browse_command=browse_command,
            )
            row += 1

        self._starting_at_variable = self._tk.BooleanVar(value=state.is_starting_at)
        self._ttk.Checkbutton(
            frame,
            text="Pricing is “Starting at”",
            variable=self._starting_at_variable,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        self._ttk.Label(frame, text="Scope Items").grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )
        scope_frame = self._ttk.Frame(frame)
        scope_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        scope_frame.columnconfigure(0, weight=1)
        self._scope_list = self._tk.Listbox(scope_frame, height=5, exportselection=False)
        self._scope_list.grid(row=0, column=0, columnspan=4, sticky="ew")
        self._scope_list.bind("<<ListboxSelect>>", self._on_scope_selected)
        self._scope_variable = self._tk.StringVar(value="")
        self._scope_entry = self._ttk.Entry(
            scope_frame,
            textvariable=self._scope_variable,
        )
        self._scope_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 4))
        for column, (text, command) in enumerate(
            (
                ("Add Scope Item", self._add_scope),
                ("Remove Scope Item", self._remove_scope),
                ("Move Up", lambda: self._move_scope(-1)),
                ("Move Down", lambda: self._move_scope(1)),
            )
        ):
            self._ttk.Button(scope_frame, text=text, command=command).grid(
                row=2,
                column=column,
                padx=(0 if column == 0 else 4, 0),
                sticky="ew",
            )
        row += 1

        self._notes_text = self._multiline_field(frame, row, "Notes", state.notes)
        row += 1
        self._terms_text = self._multiline_field(
            frame,
            row,
            "Terms and Conditions",
            state.terms_and_conditions,
        )

    def _multiline_field(
        self,
        parent: object,
        row: int,
        label: str,
        value: str,
    ) -> object:
        self._ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )
        widget = self._tk.Text(parent, height=4, wrap="word")
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        widget.insert("1.0", value)
        widget.edit_modified(False)
        return widget

    def _build_actions_section(self) -> None:
        frame = self._section("Step 4 — Validate, Generate, and Open", 7)
        buttons = self._ttk.Frame(frame)
        buttons.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._validate_button = self._ttk.Button(
            buttons,
            text="Validate Draft",
            command=self._validate,
        )
        self._generate_button = self._ttk.Button(
            buttons,
            text="Generate Proposal Draft",
            command=self._generate,
        )
        self._open_json_button = self._ttk.Button(
            buttons,
            text="Open Proposal Input JSON",
            command=self._open_json,
        )
        self._open_docx_button = self._ttk.Button(
            buttons,
            text="Open Proposal DOCX",
            command=self._open_docx,
        )
        self._open_folder_button = self._ttk.Button(
            buttons,
            text="Open Output Folder",
            command=self._open_folder,
        )
        for column, button in enumerate(
            (
                self._validate_button,
                self._generate_button,
                self._open_json_button,
                self._open_docx_button,
                self._open_folder_button,
            )
        ):
            button.grid(row=0, column=column, padx=(0 if column == 0 else 4, 0))

        self._ttk.Label(frame, text="Private Local Summary").grid(
            row=1,
            column=0,
            sticky="nw",
            pady=(10, 3),
        )
        self._summary_text = self._tk.Text(frame, height=8, wrap="word", state="disabled")
        self._summary_text.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=(10, 3),
        )
        self._status_variable = self._tk.StringVar(value="Validation required.")
        self._ttk.Label(
            frame,
            textvariable=self._status_variable,
            wraplength=760,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _bind_state_changes(self) -> None:
        for name, variable in self._variables.items():
            variable.trace_add(
                "write",
                lambda *_args, field_name=name: self._on_text_field_changed(field_name),
            )
        for name, variable in self._customer_creation_variables.items():
            variable.trace_add(
                "write",
                lambda *_args, field_name=name: (
                    self._on_customer_creation_field_changed(field_name)
                ),
            )
        for name, variable in self._customer_edit_variables.items():
            if name == "customer_id":
                continue
            variable.trace_add(
                "write",
                lambda *_args, field_name=name: (
                    self._on_customer_edit_field_changed(field_name)
                ),
            )
        for name, variable in self._job_creation_variables.items():
            variable.trace_add(
                "write",
                lambda *_args, field_name=name: (
                    self._on_job_creation_field_changed(field_name)
                ),
            )
        for name, variable in self._job_edit_variables.items():
            if name in {"job_id", "customer_id"}:
                continue
            variable.trace_add(
                "write",
                lambda *_args, field_name=name: (
                    self._on_job_edit_field_changed(field_name)
                ),
            )
        self._job_creation_contents_known_variable.trace_add(
            "write",
            lambda *_args: self._on_job_creation_contents_known_changed(),
        )
        self._job_edit_contents_known_variable.trace_add(
            "write",
            lambda *_args: self._on_job_edit_contents_known_changed(),
        )
        self._starting_at_variable.trace_add(
            "write",
            lambda *_args: self._on_starting_at_changed(),
        )
        self._scope_variable.trace_add(
            "write",
            lambda *_args: self._on_scope_description_changed(),
        )
        self._notes_text.bind(
            "<<Modified>>",
            lambda event: self._on_multiline_changed("notes", event.widget),
        )
        self._terms_text.bind(
            "<<Modified>>",
            lambda event: self._on_multiline_changed(
                "terms_and_conditions",
                event.widget,
            ),
        )
        self._customer_creation_notes_text.bind(
            "<<Modified>>",
            self._on_customer_creation_notes_changed,
        )
        self._customer_edit_notes_text.bind(
            "<<Modified>>",
            self._on_customer_edit_notes_changed,
        )
        self._job_creation_scope_notes_text.bind(
            "<<Modified>>",
            lambda event: self._on_job_creation_notes_changed("scope_notes", event),
        )
        self._job_creation_internal_notes_text.bind(
            "<<Modified>>",
            lambda event: self._on_job_creation_notes_changed("internal_notes", event),
        )
        self._job_edit_scope_notes_text.bind(
            "<<Modified>>",
            lambda event: self._on_job_edit_notes_changed("scope_notes", event),
        )
        self._job_edit_internal_notes_text.bind(
            "<<Modified>>",
            lambda event: self._on_job_edit_notes_changed("internal_notes", event),
        )

    def _on_text_field_changed(self, name: str) -> None:
        if self._updating_widgets:
            return
        self.controller.set_text_field(name, self._variables[name].get())
        if name == "database_path":
            self._customer_combo.configure(values=())
            _clear_combobox_selection(
                self._customer_combo,
                self._customer_variable,
            )
            self._job_combo.configure(values=())
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._clear_customer_edit_widgets()
        self._show_invalidated_state()

    def _on_customer_creation_field_changed(self, name: str) -> None:
        self.controller.set_customer_creation_field(
            name,
            self._customer_creation_variables[name].get(),
        )
        self._customer_creation_status_variable.set(
            "Customer details changed; click Create Customer to insert one record."
        )

    def _on_customer_creation_notes_changed(self, event: object) -> None:
        widget = event.widget
        if not widget.edit_modified():
            return
        self.controller.set_customer_creation_field(
            "notes",
            widget.get("1.0", "end-1c"),
        )
        widget.edit_modified(False)
        self._customer_creation_status_variable.set(
            "Customer details changed; click Create Customer to insert one record."
        )

    def _on_customer_edit_field_changed(self, name: str) -> None:
        if self._updating_widgets:
            return
        self.controller.set_customer_edit_field(
            name,
            self._customer_edit_variables[name].get(),
        )
        self._customer_edit_status_variable.set(
            "Customer edit fields changed; click Save Customer Changes to update."
        )

    def _on_customer_edit_notes_changed(self, event: object) -> None:
        widget = event.widget
        if self._updating_widgets or not widget.edit_modified():
            return
        self.controller.set_customer_edit_field(
            "notes",
            widget.get("1.0", "end-1c"),
        )
        widget.edit_modified(False)
        self._customer_edit_status_variable.set(
            "Customer edit fields changed; click Save Customer Changes to update."
        )

    def _on_job_creation_field_changed(self, name: str) -> None:
        self.controller.set_job_creation_field(
            name,
            self._job_creation_variables[name].get(),
        )
        self._job_creation_status_variable.set(
            "Job details changed; click Create Job to insert one record."
        )

    def _on_job_creation_contents_known_changed(self) -> None:
        self.controller.set_job_creation_contents_known(
            bool(self._job_creation_contents_known_variable.get())
        )
        self._job_creation_status_variable.set(
            "Job details changed; click Create Job to insert one record."
        )

    def _on_job_creation_notes_changed(self, name: str, event: object) -> None:
        widget = event.widget
        if not widget.edit_modified():
            return
        self.controller.set_job_creation_field(
            name,
            widget.get("1.0", "end-1c"),
        )
        widget.edit_modified(False)
        self._job_creation_status_variable.set(
            "Job details changed; click Create Job to insert one record."
        )

    def _on_job_edit_field_changed(self, name: str) -> None:
        if self._updating_widgets:
            return
        self.controller.set_job_edit_field(
            name,
            self._job_edit_variables[name].get(),
        )
        self._job_edit_status_variable.set(
            "Job edit fields changed; click Save Job Changes to update."
        )

    def _on_job_edit_contents_known_changed(self) -> None:
        if self._updating_widgets:
            return
        self.controller.set_job_edit_contents_known(
            bool(self._job_edit_contents_known_variable.get())
        )
        self._job_edit_status_variable.set(
            "Job edit fields changed; click Save Job Changes to update."
        )

    def _on_job_edit_notes_changed(self, name: str, event: object) -> None:
        widget = event.widget
        if self._updating_widgets or not widget.edit_modified():
            return
        self.controller.set_job_edit_field(
            name,
            widget.get("1.0", "end-1c"),
        )
        widget.edit_modified(False)
        self._job_edit_status_variable.set(
            "Job edit fields changed; click Save Job Changes to update."
        )

    def _on_starting_at_changed(self) -> None:
        if self._updating_widgets:
            return
        self.controller.set_starting_at(bool(self._starting_at_variable.get()))
        self._show_invalidated_state()

    def _on_multiline_changed(self, name: str, widget: object) -> None:
        if self._updating_widgets or not widget.edit_modified():
            return
        self.controller.set_text_field(name, widget.get("1.0", "end-1c"))
        widget.edit_modified(False)
        self._show_invalidated_state()

    def _selected_scope_index(self) -> int | None:
        selection = self._scope_list.curselection()
        return int(selection[0]) if selection else None

    def _on_scope_selected(self, _event: object = None) -> None:
        index = self._selected_scope_index()
        if index is None:
            return
        self._updating_widgets = True
        try:
            self._scope_variable.set(self.controller.state.scope_descriptions[index])
        finally:
            self._updating_widgets = False

    def _on_scope_description_changed(self) -> None:
        if self._updating_widgets:
            return
        index = self._selected_scope_index()
        if index is None:
            return
        self.controller.set_scope_description(index, self._scope_variable.get())
        self._refresh_scope_list(index)
        self._show_invalidated_state()

    def _add_scope(self) -> None:
        index = self.controller.add_scope_item()
        self._refresh_scope_list(index)
        self._show_invalidated_state()

    def _remove_scope(self) -> None:
        index = self._selected_scope_index()
        if index is None:
            self._show_error(DesktopFormError("Select a scope item to remove."))
            return
        self.controller.remove_scope_item(index)
        next_index = min(index, len(self.controller.state.scope_descriptions) - 1)
        self._refresh_scope_list(next_index if next_index >= 0 else None)
        self._show_invalidated_state()

    def _move_scope(self, offset: int) -> None:
        index = self._selected_scope_index()
        if index is None:
            self._show_error(DesktopFormError("Select a scope item to move."))
            return
        destination = self.controller.move_scope_item(index, offset)
        self._refresh_scope_list(destination)
        self._show_invalidated_state()

    def _refresh_scope_list(self, selected_index: int | None) -> None:
        self._scope_list.delete(0, "end")
        for number, description in self.controller.numbered_scope_items():
            self._scope_list.insert("end", f"{number}. {description}")
        if selected_index is not None and self.controller.state.scope_descriptions:
            self._scope_list.selection_set(selected_index)
            self._scope_list.activate(selected_index)
            self._scope_list.see(selected_index)
            self._on_scope_selected()
        else:
            self._updating_widgets = True
            try:
                self._scope_variable.set("")
            finally:
                self._updating_widgets = False

    def _browse_database(self) -> None:
        path = self._filedialog.askopenfilename(
            title="Select existing records database",
            filetypes=(("SQLite database", "*.sqlite *.sqlite3 *.db"), ("All files", "*")),
        )
        if path:
            self._variables["database_path"].set(path)

    def _create_records_database(self) -> None:
        selected = self._filedialog.asksaveasfilename(
            title="Create new records database",
            defaultextension=".sqlite3",
            filetypes=(
                ("SQLite database", "*.sqlite *.sqlite3 *.db"),
                ("All files", "*"),
            ),
            confirmoverwrite=False,
        )
        if not selected:
            return

        try:
            database_path = self.controller.create_records_database(selected)
            self._updating_widgets = True
            try:
                self._variables["database_path"].set(str(database_path))
            finally:
                self._updating_widgets = False
            self._clear_customer_and_job_widgets()
            self._set_summary(())
            self._status_variable.set(
                "New records database created and selected; customer creation is ready."
            )
            self._refresh_action_states()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._updating_widgets = True
            try:
                self._variables["database_path"].set("")
            finally:
                self._updating_widgets = False
            self._clear_customer_and_job_widgets()
            self._set_summary(())
            self._status_variable.set(
                "Records database creation failed; no database was selected."
            )
            self._refresh_action_states()
            self._show_error(exc)

    def _browse_template(self) -> None:
        path = self._filedialog.askopenfilename(
            title="Select existing DOCX template",
            filetypes=(("Word document", "*.docx"), ("All files", "*")),
        )
        if path:
            self._variables["template_path"].set(path)

    def _browse_output_root(self) -> None:
        path = self._filedialog.askdirectory(title="Select private output root")
        if not path:
            return
        output_folder, output_json, output_docx = self.controller.propose_output_paths(path)
        self._updating_widgets = True
        try:
            for name, value in (
                ("output_root", Path(path)),
                ("output_folder", output_folder),
                ("proposal_input_json_output_path", output_json),
                ("proposal_docx_output_path", output_docx),
            ):
                self._variables[name].set(str(value))
        finally:
            self._updating_widgets = False
        self._show_invalidated_state()

    def _browse_docx_output(self) -> None:
        current = Path(self.controller.state.proposal_docx_output_path)
        selected = self._filedialog.asksaveasfilename(
            title="Select proposal DOCX output",
            defaultextension=".docx",
            filetypes=(("Word document", "*.docx"),),
            initialdir=self.controller.state.output_folder or None,
            initialfile=current.name or "proposal.docx",
            confirmoverwrite=True,
        )
        if not selected:
            self._status_variable.set(
                "Output selection cancelled; no file was created."
            )
            self._refresh_action_states()
            return
        try:
            output_folder, output_json, output_docx = (
                self.controller.select_docx_output_path(selected)
            )
            self._updating_widgets = True
            try:
                for name, value in (
                    ("output_root", output_folder),
                    ("output_folder", output_folder),
                    ("proposal_input_json_output_path", output_json),
                    ("proposal_docx_output_path", output_docx),
                ):
                    self._variables[name].set(str(value))
            finally:
                self._updating_widgets = False
            self._set_summary(())
            self._status_variable.set(
                "DOCX output selected; validate the current draft before generation."
            )
            self._refresh_action_states()
        except ExistingOutputPathError as exc:
            self._status_variable.set(
                "Overwrite rejected; the existing file was not changed."
            )
            self._refresh_action_states()
            self._show_error(exc)
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._status_variable.set(
                "Output selection failed; choose a valid private DOCX path."
            )
            self._refresh_action_states()
            self._show_error(exc)

    def _load_customers(self) -> None:
        try:
            self.controller.load_customers()
            self._customer_combo.configure(
                values=self.controller.customer_display_labels,
            )
            _clear_combobox_selection(
                self._customer_combo,
                self._customer_variable,
            )
            self._job_combo.configure(values=())
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._clear_customer_edit_widgets()
            self._clear_job_edit_widgets()
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._clear_customer_and_job_widgets()
            self._show_invalidated_state()
            self._show_error(exc)

    def _create_customer(self) -> None:
        try:
            created = self.controller.create_customer()
            self._customer_combo.configure(
                values=self.controller.customer_display_labels,
            )
            _clear_combobox_selection(
                self._customer_combo,
                self._customer_variable,
            )
            self._job_combo.configure(values=())
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._clear_customer_edit_widgets()
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
            self._customer_creation_status_variable.set(
                f"Customer {created.customer_id} created; customers reloaded."
            )
        except CustomerAlreadyExistsError as exc:
            self._customer_creation_status_variable.set(
                "Duplicate customer ID rejected; the existing customer was unchanged."
            )
            self._show_error(exc)
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._customer_creation_status_variable.set(
                "Customer creation failed; review the error before retrying."
            )
            self._show_error(exc)

    def _update_customer(self) -> None:
        try:
            updated = self.controller.update_customer()
            self._customer_combo.configure(
                values=self.controller.customer_display_labels,
            )
            selected_index = next(
                (
                    index
                    for index, customer in enumerate(self.controller.customers)
                    if customer.customer_id == updated.customer_id
                ),
                None,
            )
            if selected_index is None:
                raise DesktopFormError(
                    "Customer updated, but the refreshed selection is unavailable."
                )
            self._customer_combo.current(selected_index)
            self._customer_variable.set(
                self.controller.customer_display_labels[selected_index]
            )
            self._job_combo.configure(values=self.controller.job_display_labels)
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._refresh_customer_edit_widgets()
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
            self._customer_edit_status_variable.set(
                "Customer updated; customers and selected-customer jobs reloaded."
            )
        except NoCustomerChangesError:
            self._customer_edit_status_variable.set("No customer changes to save.")
        except CustomerNotFoundError as exc:
            self._customer_edit_status_variable.set(
                "Customer is missing; reload customers before retrying."
            )
            self._show_error(exc)
        except CustomerUpdateConflictError as exc:
            self._customer_edit_status_variable.set(
                "Customer changed elsewhere; reload customers before retrying."
            )
            self._show_error(exc)
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._customer_edit_status_variable.set(
                "Customer update failed; review the error before retrying."
            )
            self._show_error(exc)

    def _create_job(self) -> None:
        try:
            created = self.controller.create_job()
            self._job_combo.configure(values=self.controller.job_display_labels)
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
            self._job_creation_status_variable.set(
                f"Job {created.job_id} created; selected-customer jobs reloaded."
            )
        except JobAlreadyExistsError as exc:
            self._job_creation_status_variable.set(
                "Duplicate job ID rejected; the existing job was unchanged."
            )
            self._show_error(exc)
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._job_creation_status_variable.set(
                "Job creation failed; review the error before retrying."
            )
            self._show_error(exc)

    def _update_job(self) -> None:
        try:
            updated = self.controller.update_job()
            self._job_combo.configure(values=self.controller.job_display_labels)
            selected_index = next(
                (
                    index
                    for index, job in enumerate(self.controller.jobs)
                    if job.job_id == updated.job_id
                ),
                None,
            )
            if selected_index is None:
                raise DesktopFormError(
                    "Job updated, but the refreshed selection is unavailable."
                )
            self._job_combo.current(selected_index)
            self._job_variable.set(self.controller.job_display_labels[selected_index])
            self._refresh_job_edit_widgets()
            self._show_invalidated_state()
            self._job_edit_status_variable.set(
                "Job updated; selected-customer jobs reloaded."
            )
        except NoJobChangesError:
            self._job_edit_status_variable.set("No job changes to save.")
        except JobNotFoundError as exc:
            self._job_edit_status_variable.set(
                "Job is missing; reload jobs before retrying."
            )
            self._show_error(exc)
        except JobUpdateConflictError as exc:
            self._job_edit_status_variable.set(
                "Job changed elsewhere; reload jobs before retrying."
            )
            self._show_error(exc)
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._job_edit_status_variable.set(
                "Job update failed; review the error before retrying."
            )
            self._show_error(exc)

    def _on_customer_selected(self, _event: object = None) -> None:
        try:
            index = self._customer_combo.current()
            if index < 0:
                customer_id = ""
            elif index >= len(self.controller.customers):
                self.controller.select_customer("")
                raise DesktopFormError("Select an existing loaded customer.")
            else:
                customer_id = self.controller.customers[index].customer_id
            self.controller.select_customer(customer_id)
            self._job_combo.configure(values=self.controller.job_display_labels)
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._refresh_customer_edit_widgets()
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._clear_customer_and_job_widgets()
            self._show_invalidated_state()
            self._show_error(exc)

    def _on_job_selected(self, _event: object = None) -> None:
        try:
            index = self._job_combo.current()
            if index < 0:
                job_id = ""
            elif index >= len(self.controller.jobs):
                self.controller.select_job("")
                raise DesktopFormError("Select an existing loaded job.")
            else:
                job_id = self.controller.jobs[index].job_id
            self.controller.select_job(job_id)
            self._refresh_job_edit_widgets()
            self._show_invalidated_state()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            _clear_combobox_selection(self._job_combo, self._job_variable)
            self._clear_job_edit_widgets()
            self._show_invalidated_state()
            self._show_error(exc)

    def _validate(self) -> None:
        try:
            result = self.controller.validate_draft()
            self._set_summary(result.summary_lines)
            self._status_variable.set("Validation passed. Generation is enabled.")
            self._refresh_action_states()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._set_summary(())
            self._status_variable.set("Validation failed; review the error and revalidate.")
            self._refresh_action_states()
            self._show_error(exc)

    def _generate(self) -> None:
        try:
            result = self.controller.generate_draft()
            self._status_variable.set(
                "Generated local artifacts:\n"
                f"{result.proposal_input_json_path}\n{result.proposal_docx_path}"
            )
            self._refresh_action_states()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            if self.controller.validated_request is None:
                self._set_summary(())
                self._status_variable.set(
                    "Generation blocked; revalidation is required."
                )
            else:
                self._status_variable.set(
                    "Generation failed; the unchanged validated draft may be retried."
                )
            self._refresh_action_states()
            self._show_error(exc)

    def _open_json(self) -> None:
        self._run_open_action(self.controller.open_proposal_input_json)

    def _open_docx(self) -> None:
        self._run_open_action(self.controller.open_proposal_docx)

    def _open_folder(self) -> None:
        self._run_open_action(self.controller.open_output_folder)

    def _run_open_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - final local GUI boundary.
            self._show_error(exc)

    def _show_invalidated_state(self) -> None:
        self._set_summary(())
        self._status_variable.set("Draft changed; validation required.")
        self._refresh_action_states()

    def _clear_customer_and_job_widgets(self) -> None:
        self._customer_combo.configure(values=())
        _clear_combobox_selection(
            self._customer_combo,
            self._customer_variable,
        )
        self._job_combo.configure(values=())
        _clear_combobox_selection(self._job_combo, self._job_variable)
        self._clear_customer_edit_widgets()
        self._clear_job_edit_widgets()

    def _clear_customer_edit_widgets(self) -> None:
        self._updating_widgets = True
        try:
            for variable in self._customer_edit_variables.values():
                variable.set("")
            self._customer_edit_notes_text.delete("1.0", "end")
            self._customer_edit_notes_text.edit_modified(False)
        finally:
            self._updating_widgets = False
        self._customer_edit_status_variable.set(
            "Select an existing customer to edit."
        )

    def _refresh_customer_edit_widgets(self) -> None:
        state = self.controller.customer_edit_state
        self._updating_widgets = True
        try:
            for name, variable in self._customer_edit_variables.items():
                variable.set(getattr(state, name))
            self._customer_edit_notes_text.delete("1.0", "end")
            if state.notes:
                self._customer_edit_notes_text.insert("1.0", state.notes)
            self._customer_edit_notes_text.edit_modified(False)
        finally:
            self._updating_widgets = False
        if state.customer_id:
            self._customer_edit_status_variable.set(
                "Customer edit form loaded; changes require explicit Save Customer Changes."
            )
        else:
            self._customer_edit_status_variable.set(
                "Select an existing customer to edit."
            )

    def _clear_job_edit_widgets(self) -> None:
        self._updating_widgets = True
        try:
            for variable in self._job_edit_variables.values():
                variable.set("")
            self._job_edit_contents_known_variable.set(False)
            for widget in (
                self._job_edit_scope_notes_text,
                self._job_edit_internal_notes_text,
            ):
                widget.delete("1.0", "end")
                widget.edit_modified(False)
        finally:
            self._updating_widgets = False
        self._job_edit_status_variable.set("Select an existing job to edit.")

    def _refresh_job_edit_widgets(self) -> None:
        state = self.controller.job_edit_state
        self._updating_widgets = True
        try:
            for name, variable in self._job_edit_variables.items():
                variable.set(getattr(state, name))
            self._job_edit_contents_known_variable.set(state.contents_known)
            for widget, value in (
                (self._job_edit_scope_notes_text, state.scope_notes),
                (self._job_edit_internal_notes_text, state.internal_notes),
            ):
                widget.delete("1.0", "end")
                if value:
                    widget.insert("1.0", value)
                widget.edit_modified(False)
        finally:
            self._updating_widgets = False
        if state.job_id:
            self._job_edit_status_variable.set(
                "Job edit form loaded; changes require explicit Save Job Changes."
            )
        else:
            self._job_edit_status_variable.set("Select an existing job to edit.")

    def _set_summary(self, lines: tuple[str, ...]) -> None:
        self._summary_text.configure(state="normal")
        self._summary_text.delete("1.0", "end")
        if lines:
            self._summary_text.insert("1.0", "\n".join(lines))
        self._summary_text.configure(state="disabled")

    def _show_error(self, error: Exception) -> None:
        self._messagebox.showerror("Phoenix Office", str(error), parent=self._root)
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        self._generate_button.configure(
            state="normal" if self.controller.generation_enabled else "disabled"
        )
        open_state = "normal" if self.controller.open_actions_enabled else "disabled"
        self._open_json_button.configure(state=open_state)
        self._open_docx_button.configure(state=open_state)
        self._open_folder_button.configure(state=open_state)


def main() -> int:
    """Run one local foreground Tk process."""

    tk, ttk, filedialog, messagebox = _load_tkinter()
    root = tk.Tk()
    ProposalDesktopApp(
        root,
        toolkit=(tk, ttk, filedialog, messagebox),
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
