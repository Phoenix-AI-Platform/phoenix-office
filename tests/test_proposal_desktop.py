"""Focused headless tests for the read-only local proposal desktop adapter."""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

import phoenix_office.proposal_build as proposal_build
import phoenix_office.proposal_desktop as proposal_desktop
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
)
from phoenix_office.records import (
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    CustomerUpdateConflictError,
    JobAlreadyExistsError,
    JobNotFoundError,
    JobUpdateConflictError,
    SQLiteCustomerRepository,
    SQLiteJobRepository,
)

NOW = datetime(2026, 7, 30, 14, 5, 6)
ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / "tests" / "fixtures" / "templates" / "a1_proposal_template.docx"


def _customer(
    customer_id: str = "customer-synthetic-001",
    display_name: str = "Synthetic Customer",
) -> CustomerRecord:
    return CustomerRecord(customer_id=customer_id, display_name=display_name)


def _job(
    job_id: str = "job-synthetic-001",
    customer_id: str = "customer-synthetic-001",
    job_name: str = "Synthetic Tank Project",
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        customer_id=customer_id,
        job_name=job_name,
        site_street_address="100 Example Ave.",
        site_city_state_zip="Example, WI 00000",
    )


@dataclass(slots=True)
class ControllerHarness:
    controller: proposal_desktop.ProposalDesktopController
    customer_factory_calls: list[tuple[Path, bool, bool]]
    customer_creation_factory_calls: list[tuple[Path, bool, bool]]
    customer_create_calls: list[CustomerRecord]
    customer_update_factory_calls: list[tuple[Path, bool, bool]]
    customer_update_calls: list[tuple[CustomerRecord, CustomerRecord]]
    job_factory_calls: list[tuple[Path, bool, bool]]
    job_list_calls: list[str]
    job_creation_factory_calls: list[tuple[Path, bool, bool]]
    job_create_calls: list[JobRecord]
    job_update_factory_calls: list[tuple[Path, bool, bool]]
    job_update_calls: list[tuple[JobRecord, JobRecord]]
    validation_calls: list[ProposalDraftBuildRequest]
    build_calls: list[ProposalDraftBuildRequest]
    opened_paths: list[Path]


class FakeVariable:
    def __init__(self, value: Any = "") -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class FakeCombo:
    def __init__(self, *, values: tuple[str, ...] = (), current: int = -1) -> None:
        self.values = values
        self.current_index = current
        self.value = values[current] if 0 <= current < len(values) else ""

    def configure(self, **kwargs: object) -> None:
        if "values" in kwargs:
            self.values = tuple(kwargs["values"])  # type: ignore[arg-type]

    def current(self, index: int | None = None) -> int:
        if index is not None:
            if index < 0:
                raise AssertionError(
                    "ttk.Combobox.current(index) does not accept negative indexes"
                )
            self.current_index = index
            self.value = self.values[index] if index < len(self.values) else ""
        return self.current_index

    def set(self, value: str) -> None:
        self.value = value
        self.current_index = self.values.index(value) if value in self.values else -1


class FakeText:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.state = "disabled"
        self.modified = False

    def configure(self, **kwargs: object) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])

    def delete(self, _start: str, _end: str) -> None:
        self.content = ""

    def insert(self, _start: str, value: str) -> None:
        self.content = value

    def get(self, _start: str, _end: str) -> str:
        return self.content

    def edit_modified(self, value: bool | None = None) -> bool:
        if value is not None:
            self.modified = value
        return self.modified


class FakeButton:
    def __init__(self) -> None:
        self.state = "disabled"

    def configure(self, **kwargs: object) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])


class FakeMessagebox:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, object]] = []

    def showerror(self, title: str, message: str, *, parent: object) -> None:
        self.errors.append((title, message, parent))


class FakeFileDialog:
    def __init__(self, save_result: str = "") -> None:
        self.save_result = save_result
        self.save_calls: list[dict[str, object]] = []

    def asksaveasfilename(self, **kwargs: object) -> str:
        self.save_calls.append(kwargs)
        return self.save_result


@dataclass(slots=True)
class AppHarness:
    app: proposal_desktop.ProposalDesktopApp
    customer_combo: FakeCombo
    job_combo: FakeCombo
    customer_variable: FakeVariable
    job_variable: FakeVariable
    summary_text: FakeText
    status_variable: FakeVariable
    generate_button: FakeButton
    open_buttons: tuple[FakeButton, FakeButton, FakeButton]
    messagebox: FakeMessagebox
    filedialog: FakeFileDialog
    customer_creation_status_variable: FakeVariable
    customer_edit_status_variable: FakeVariable
    job_creation_status_variable: FakeVariable
    job_edit_status_variable: FakeVariable


def _headless_app(
    controller: proposal_desktop.ProposalDesktopController,
) -> AppHarness:
    app = object.__new__(proposal_desktop.ProposalDesktopApp)
    customer_combo = FakeCombo(values=controller.customer_display_labels)
    job_combo = FakeCombo(values=controller.job_display_labels)
    customer_variable = FakeVariable()
    job_variable = FakeVariable()
    summary_text = FakeText("\n".join(controller.validation_summary_lines))
    status_variable = FakeVariable("Previous successful state")
    generate_button = FakeButton()
    open_buttons = (FakeButton(), FakeButton(), FakeButton())
    messagebox = FakeMessagebox()
    filedialog = FakeFileDialog()
    customer_creation_status_variable = FakeVariable(
        "No customer creation requested."
    )
    customer_edit_status_variable = FakeVariable(
        "Select an existing customer to edit."
    )
    job_creation_status_variable = FakeVariable("No job creation requested.")
    job_edit_status_variable = FakeVariable("Select an existing job to edit.")
    app.controller = controller
    app._root = object()
    app._messagebox = messagebox
    app._filedialog = filedialog
    app._updating_widgets = False
    app._variables = {
        name: FakeVariable(str(getattr(controller.state, name)))
        for name in (
            "database_path",
            "output_root",
            "output_folder",
            "proposal_input_json_output_path",
            "proposal_docx_output_path",
        )
    }
    app._customer_creation_variables = {
        name: FakeVariable(str(getattr(controller.customer_creation_state, name)))
        for name in (
            "customer_id",
            "display_name",
            "phone",
            "email",
            "billing_street_address",
            "billing_city_state_zip",
        )
    }
    app._customer_creation_notes_text = FakeText(
        controller.customer_creation_state.notes
    )
    app._customer_creation_status_variable = customer_creation_status_variable
    app._customer_edit_variables = {
        name: FakeVariable(getattr(controller.customer_edit_state, name))
        for name in (
            "customer_id",
            "display_name",
            "phone",
            "email",
            "billing_street_address",
            "billing_city_state_zip",
        )
    }
    app._customer_edit_notes_text = FakeText(controller.customer_edit_state.notes)
    app._customer_edit_status_variable = customer_edit_status_variable
    app._job_creation_variables = {
        name: FakeVariable(getattr(controller.job_creation_state, name))
        for name in (
            "job_id",
            "job_name",
            "site_street_address",
            "site_city_state_zip",
            "status",
            "tank_location_type",
            "tank_size_gallons",
            "tank_contents",
        )
    }
    app._job_creation_contents_known_variable = FakeVariable(
        controller.job_creation_state.contents_known
    )
    app._job_creation_scope_notes_text = FakeText(
        controller.job_creation_state.scope_notes
    )
    app._job_creation_internal_notes_text = FakeText(
        controller.job_creation_state.internal_notes
    )
    app._job_creation_status_variable = job_creation_status_variable
    app._job_edit_variables = {
        name: FakeVariable(getattr(controller.job_edit_state, name))
        for name in (
            "job_id",
            "customer_id",
            "job_name",
            "site_street_address",
            "site_city_state_zip",
            "status",
            "tank_location_type",
            "tank_size_gallons",
            "tank_contents",
        )
    }
    app._job_edit_contents_known_variable = FakeVariable(
        controller.job_edit_state.contents_known
    )
    app._job_edit_scope_notes_text = FakeText(controller.job_edit_state.scope_notes)
    app._job_edit_internal_notes_text = FakeText(
        controller.job_edit_state.internal_notes
    )
    app._job_edit_status_variable = job_edit_status_variable
    app._customer_combo = customer_combo
    app._job_combo = job_combo
    app._customer_variable = customer_variable
    app._job_variable = job_variable
    app._summary_text = summary_text
    app._status_variable = status_variable
    app._generate_button = generate_button
    app._open_json_button, app._open_docx_button, app._open_folder_button = (
        open_buttons
    )
    app._refresh_action_states()
    return AppHarness(
        app=app,
        customer_combo=customer_combo,
        job_combo=job_combo,
        customer_variable=customer_variable,
        job_variable=job_variable,
        summary_text=summary_text,
        status_variable=status_variable,
        generate_button=generate_button,
        open_buttons=open_buttons,
        messagebox=messagebox,
        filedialog=filedialog,
        customer_creation_status_variable=customer_creation_status_variable,
        customer_edit_status_variable=customer_edit_status_variable,
        job_creation_status_variable=job_creation_status_variable,
        job_edit_status_variable=job_edit_status_variable,
    )


def _configured_controller(
    tmp_path: Path,
    *,
    customers: tuple[CustomerRecord, ...] | None = None,
    jobs: tuple[JobRecord, ...] | None = None,
) -> ControllerHarness:
    customer_records = list(customers or (
        _customer(),
        _customer("customer-synthetic-002", "Synthetic Customer"),
    ))
    job_records = list(jobs or (
        _job(),
        _job("job-synthetic-002", job_name="Synthetic Inspection"),
        _job(
            "job-synthetic-003",
            customer_id="customer-synthetic-002",
            job_name="Synthetic Secondary Project",
        ),
    ))
    customer_factory_calls: list[tuple[Path, bool, bool]] = []
    customer_creation_factory_calls: list[tuple[Path, bool, bool]] = []
    customer_create_calls: list[CustomerRecord] = []
    customer_update_factory_calls: list[tuple[Path, bool, bool]] = []
    customer_update_calls: list[tuple[CustomerRecord, CustomerRecord]] = []
    job_factory_calls: list[tuple[Path, bool, bool]] = []
    job_list_calls: list[str] = []
    job_creation_factory_calls: list[tuple[Path, bool, bool]] = []
    job_create_calls: list[JobRecord] = []
    job_update_factory_calls: list[tuple[Path, bool, bool]] = []
    job_update_calls: list[tuple[JobRecord, JobRecord]] = []
    validation_calls: list[ProposalDraftBuildRequest] = []
    build_calls: list[ProposalDraftBuildRequest] = []
    opened_paths: list[Path] = []

    class CustomerRepository:
        def list_customers(self) -> list[CustomerRecord]:
            return list(customer_records)

        def get_customer(self, customer_id: str) -> CustomerRecord | None:
            return next(
                (
                    customer
                    for customer in customer_records
                    if customer.customer_id == customer_id
                ),
                None,
            )

    class CustomerCreationRepository:
        def create_customer(self, record: CustomerRecord) -> CustomerRecord:
            if any(
                customer.customer_id == record.customer_id
                for customer in customer_records
            ):
                raise CustomerAlreadyExistsError(
                    "Customer ID already exists; no customer was changed."
                )
            customer_records.append(record)
            customer_create_calls.append(record)
            return record

    class CustomerUpdateRepository:
        def update_customer(
            self,
            record: CustomerRecord,
            expected_original: CustomerRecord,
        ) -> CustomerRecord:
            index = next(
                (
                    index
                    for index, customer in enumerate(customer_records)
                    if customer.customer_id == record.customer_id
                ),
                None,
            )
            if index is None:
                raise CustomerNotFoundError(
                    "Customer no longer exists; reload customers before retrying."
                )
            if customer_records[index] != expected_original:
                raise CustomerUpdateConflictError(
                    "Customer changed elsewhere; reload customers before retrying."
                )
            customer_records[index] = record
            customer_update_calls.append((record, expected_original))
            return record

    class JobRepository:
        def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
            job_list_calls.append(customer_id)
            return [job for job in job_records if job.customer_id == customer_id]

    class JobCreationRepository:
        def create_job(self, record: JobRecord) -> JobRecord:
            if any(job.job_id == record.job_id for job in job_records):
                raise JobAlreadyExistsError(
                    "Job ID already exists; no job was changed."
                )
            job_records.append(record)
            job_create_calls.append(record)
            return record

    class JobUpdateRepository:
        def update_job(
            self,
            record: JobRecord,
            expected_original: JobRecord,
        ) -> JobRecord:
            index = next(
                (
                    index
                    for index, job in enumerate(job_records)
                    if job.job_id == record.job_id
                ),
                None,
            )
            if index is None:
                raise JobNotFoundError(
                    "Job no longer exists; reload jobs before retrying."
                )
            if job_records[index] != expected_original:
                raise JobUpdateConflictError(
                    "Job changed elsewhere; reload jobs before retrying."
                )
            job_records[index] = record
            job_update_calls.append((record, expected_original))
            return record

    def customer_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        customer_factory_calls.append((database_path, initialize, read_only))
        return CustomerRepository()

    def job_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        job_factory_calls.append((database_path, initialize, read_only))
        return JobRepository()

    def customer_update_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        customer_update_factory_calls.append((database_path, initialize, read_only))
        return CustomerUpdateRepository()

    def customer_creation_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        customer_creation_factory_calls.append(
            (database_path, initialize, read_only)
        )
        return CustomerCreationRepository()

    def job_creation_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        job_creation_factory_calls.append((database_path, initialize, read_only))
        return JobCreationRepository()

    def job_update_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> Any:
        job_update_factory_calls.append((database_path, initialize, read_only))
        return JobUpdateRepository()

    def validate(request: ProposalDraftBuildRequest) -> ProposalDraftValidationResult:
        validation_calls.append(request)
        return ProposalDraftValidationResult(
            proposal=object(),  # type: ignore[arg-type]
            summary_lines=(
                "Customer: Synthetic Customer",
                "Site Address: 100 Example Ave., Example, WI 00000",
                "Item Description: Explicit synthetic work",
                "Total: $125.00",
                "Company: Synthetic Services",
            ),
        )

    def build(request: ProposalDraftBuildRequest) -> ProposalDraftBuildResult:
        build_calls.append(request)
        return ProposalDraftBuildResult(
            proposal_input=object(),  # type: ignore[arg-type]
            proposal_input_json_path=request.proposal_input_json_output_path,
            proposal_docx_path=request.proposal_docx_output_path,
            summary_lines=("Customer: Synthetic Customer",),
        )

    controller = proposal_desktop.ProposalDesktopController(
        validation_function=validate,
        build_function=build,
        customer_repository_factory=customer_factory,
        customer_creation_repository_factory=customer_creation_factory,
        customer_update_repository_factory=customer_update_factory,
        job_repository_factory=job_factory,
        job_creation_repository_factory=job_creation_factory,
        job_update_repository_factory=job_update_factory,
        path_opener=opened_paths.append,
        clock=lambda: NOW,
    )
    controller.set_text_field("database_path", str(tmp_path / "records.sqlite"))
    controller.set_text_field("template_path", str(tmp_path / "template.docx"))
    controller.propose_output_paths(tmp_path / "private-output")
    controller.set_text_field("item_description", "Explicit synthetic work")
    controller.set_scope_description(0, "Perform explicit synthetic task")
    controller.add_scope_item("Leave synthetic site orderly")
    controller.set_text_field("amount", "125.00")
    controller.set_text_field("notes", "First explicit note\n\nSecond explicit note")
    controller.set_text_field("company_name", "Synthetic Services")
    controller.load_customers()
    controller.select_customer("customer-synthetic-001")
    controller.select_job("job-synthetic-001")
    return ControllerHarness(
        controller=controller,
        customer_factory_calls=customer_factory_calls,
        customer_creation_factory_calls=customer_creation_factory_calls,
        customer_create_calls=customer_create_calls,
        customer_update_factory_calls=customer_update_factory_calls,
        customer_update_calls=customer_update_calls,
        job_factory_calls=job_factory_calls,
        job_list_calls=job_list_calls,
        job_creation_factory_calls=job_creation_factory_calls,
        job_create_calls=job_create_calls,
        job_update_factory_calls=job_update_factory_calls,
        job_update_calls=job_update_calls,
        validation_calls=validation_calls,
        build_calls=build_calls,
        opened_paths=opened_paths,
    )


def _seed_database(database_path: Path) -> None:
    customer_repository = SQLiteCustomerRepository(database_path)
    job_repository = SQLiteJobRepository(database_path)
    customer_repository.save_customer(_customer())
    job_repository.save_job(_job())


def _database_hash(database_path: Path) -> str:
    return hashlib.sha256(database_path.read_bytes()).hexdigest()


def _set_valid_job_creation_fields(
    controller: proposal_desktop.ProposalDesktopController,
    *,
    job_id: str = "job-created-001",
) -> None:
    for name, value in {
        "job_id": job_id,
        "job_name": "Created Synthetic Job",
        "site_street_address": "300 Synthetic Ave.",
        "site_city_state_zip": "Example, WI 00000",
    }.items():
        controller.set_job_creation_field(name, value)


def _configure_real_validation_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> proposal_desktop.ProposalDesktopController:
    database_path = tmp_path / "records.sqlite"
    _seed_database(database_path)
    template_path = tmp_path / "template.docx"
    shutil.copyfile(TEMPLATE, template_path)

    def renderer_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("desktop validation must not invoke the DOCX renderer")

    monkeypatch.setattr(proposal_build, "DocxProposalRenderer", renderer_must_not_run)
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))
    controller.set_text_field("template_path", str(template_path))
    controller.propose_output_paths(tmp_path / "private-output")
    controller.set_text_field("item_description", "Explicit synthetic work")
    controller.set_scope_description(0, "Perform explicit synthetic task")
    controller.set_text_field("amount", "125.00")
    controller.set_text_field("company_name", "Synthetic Services")
    controller.load_customers()
    controller.select_customer("customer-synthetic-001")
    controller.select_job("job-synthetic-001")
    return controller


def test_module_import_is_headless_safe_and_does_not_import_tkinter() -> None:
    script = (
        "import sys; import phoenix_office.proposal_desktop; "
        "assert 'tkinter' not in sys.modules"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_fake_combo_matches_real_tk_negative_index_and_safe_clear_behavior() -> None:
    combo = FakeCombo(values=("Synthetic Customer",))
    combo.current(0)

    with pytest.raises(AssertionError, match="does not accept negative indexes"):
        combo.current(-1)

    combo.set("")

    assert combo.current() == -1
    assert combo.value == ""


def test_production_combobox_clearing_never_selects_a_negative_index() -> None:
    source = inspect.getsource(proposal_desktop)

    assert ".current(-1)" not in source
    assert "_clear_combobox_selection" in source


def test_initial_defaults_are_explicit_and_do_not_invent_business_values() -> None:
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)

    assert controller.state.proposal_date == "2026-07-30"
    assert controller.state.is_starting_at is False
    assert controller.state.starting_at_label == "Starting at"
    assert controller.state.total_label == "TOTAL"
    assert controller.state.proposal_input_json_output_path == "proposal_input.json"
    assert controller.state.proposal_docx_output_path == "proposal.docx"
    assert controller.state.scope_descriptions == [""]
    assert controller.state.item_description == ""
    assert controller.state.amount == ""
    assert controller.state.pricing_note == ""
    assert controller.state.notes == ""
    assert controller.state.company_name == ""
    assert controller.state.terms_and_conditions == ""
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.customer_creation_state == proposal_desktop.CustomerCreationState()
    assert controller.customer_edit_state == proposal_desktop.CustomerEditState()
    assert controller.customer_edit_expected_original is None


def test_explicit_customer_fields_construct_only_the_persisted_customer_values(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    explicit_values = {
        "customer_id": "  customer-created-001  ",
        "display_name": "  Created Synthetic Customer  ",
        "phone": "  555-0100  ",
        "email": "  created@example.invalid  ",
        "billing_street_address": "  200 Synthetic Ave.  ",
        "billing_city_state_zip": "  Example, WI 00000  ",
        "notes": " First explicit note\n\n Second explicit note  ",
    }
    for name, value in explicit_values.items():
        controller.set_customer_creation_field(name, value)

    record = controller.create_customer_record()

    assert record == CustomerRecord(
        customer_id="customer-created-001",
        display_name="Created Synthetic Customer",
        phone="555-0100",
        email="created@example.invalid",
        billing_street_address="200 Synthetic Ave.",
        billing_city_state_zip="Example, WI 00000",
        notes=["First explicit note", "Second explicit note"],
    )
    assert record.job_street_address is None
    assert record.job_city_state_zip is None
    assert harness.customer_creation_factory_calls == []
    assert harness.customer_create_calls == []


def test_blank_optional_customer_fields_become_none_without_invented_values(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_customer_creation_field("customer_id", "customer-created-002")
    controller.set_customer_creation_field("display_name", "Created Customer")
    for field_name in (
        "phone",
        "email",
        "billing_street_address",
        "billing_city_state_zip",
    ):
        controller.set_customer_creation_field(field_name, "  ")
    controller.set_customer_creation_field("notes", "\n   \n")

    record = controller.create_customer_record()

    assert record.phone is None
    assert record.email is None
    assert record.billing_street_address is None
    assert record.billing_city_state_zip is None
    assert record.notes == []
    assert record.job_street_address is None
    assert record.job_city_state_zip is None


@pytest.mark.parametrize("missing_field", ["customer_id", "display_name"])
def test_invalid_required_customer_data_performs_no_write(
    tmp_path: Path,
    missing_field: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_customer_creation_field("customer_id", "customer-created-003")
    controller.set_customer_creation_field("display_name", "Created Customer")
    controller.set_customer_creation_field(missing_field, "   ")

    with pytest.raises(proposal_desktop.DesktopFormError, match="required"):
        controller.create_customer()

    assert harness.customer_creation_factory_calls == []
    assert harness.customer_create_calls == []


def test_explicit_customer_creation_uses_write_once_then_read_only_reload(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    read_calls_before = len(harness.customer_factory_calls)
    job_calls_before = len(harness.job_factory_calls)
    controller.set_customer_creation_field("customer_id", "customer-created-004")
    controller.set_customer_creation_field("display_name", "Created Customer")

    created = controller.create_customer()

    database_path = tmp_path / "records.sqlite"
    assert created.customer_id == "customer-created-004"
    assert harness.customer_creation_factory_calls == [
        (database_path, False, False)
    ]
    assert harness.customer_create_calls == [created]
    assert len(harness.customer_factory_calls) == read_calls_before + 1
    assert harness.customer_factory_calls[-1] == (database_path, False, True)
    assert len(harness.job_factory_calls) == job_calls_before
    assert controller.customers[-1] == created
    assert controller.jobs == ()
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.generation_enabled is False


def test_duplicate_customer_creation_rejects_without_overwrite_or_reload(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    original = controller.customers[0]
    read_calls_before = len(harness.customer_factory_calls)
    controller.set_customer_creation_field("customer_id", original.customer_id)
    controller.set_customer_creation_field("display_name", "Replacement Attempt")

    with pytest.raises(CustomerAlreadyExistsError, match="already exists"):
        controller.create_customer()

    assert harness.customer_creation_factory_calls == [
        (tmp_path / "records.sqlite", False, False)
    ]
    assert harness.customer_create_calls == []
    assert len(harness.customer_factory_calls) == read_calls_before
    assert controller.customers[0] == original
    assert controller.customers[0].display_name == "Synthetic Customer"


def test_customer_form_editing_does_not_open_writable_repository_until_button_action(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    app = app_harness.app
    app._customer_creation_variables["customer_id"].set("customer-created-005")
    app._customer_creation_variables["display_name"].set("Created Customer")

    app._on_customer_creation_field_changed("customer_id")
    app._on_customer_creation_field_changed("display_name")

    assert harness.customer_creation_factory_calls == []
    assert harness.customer_create_calls == []
    assert app_harness.customer_creation_status_variable.value.startswith(
        "Customer details changed"
    )

    app._create_customer()

    assert harness.customer_creation_factory_calls == [
        (tmp_path / "records.sqlite", False, False)
    ]
    assert len(harness.customer_create_calls) == 1
    assert app_harness.customer_creation_status_variable.value == (
        "Customer customer-created-005 created; customers reloaded."
    )
    assert app_harness.customer_combo.current() == -1
    assert app_harness.job_combo.current() == -1
    assert app_harness.messagebox.errors == []


@pytest.mark.parametrize(
    ("customer_id", "display_name", "expected_status"),
    [
        (
            "customer-synthetic-001",
            "Replacement Attempt",
            "Duplicate customer ID rejected",
        ),
        ("", "Created Customer", "Customer creation failed"),
    ],
)
def test_gui_customer_creation_failures_are_controlled_and_write_nothing(
    tmp_path: Path,
    customer_id: str,
    display_name: str,
    expected_status: str,
) -> None:
    harness = _configured_controller(tmp_path)
    original = harness.controller.customers[0]
    harness.controller.set_customer_creation_field("customer_id", customer_id)
    harness.controller.set_customer_creation_field("display_name", display_name)
    app_harness = _headless_app(harness.controller)

    app_harness.app._create_customer()

    assert app_harness.customer_creation_status_variable.value.startswith(
        expected_status
    )
    assert len(app_harness.messagebox.errors) == 1
    assert harness.customer_create_calls == []
    assert harness.controller.customers[0] == original
    assert harness.controller.customers[0].display_name == "Synthetic Customer"


def test_customer_selection_populates_edit_state_and_exact_loaded_snapshot(
    tmp_path: Path,
) -> None:
    customer = CustomerRecord(
        customer_id="customer-synthetic-001",
        display_name="Original Synthetic Customer",
        phone="555-0100",
        email="original@example.invalid",
        billing_street_address="100 Synthetic Ave.",
        billing_city_state_zip="Example, WI 00000",
        notes=["First note", "Second note"],
    )
    harness = _configured_controller(tmp_path, customers=(customer,), jobs=())
    controller = harness.controller

    assert controller.customer_edit_expected_original is customer
    assert controller.customer_edit_state == proposal_desktop.CustomerEditState(
        customer_id=customer.customer_id,
        display_name=customer.display_name,
        phone=customer.phone or "",
        email=customer.email or "",
        billing_street_address=customer.billing_street_address or "",
        billing_city_state_zip=customer.billing_city_state_zip or "",
        notes="First note\nSecond note",
    )


def test_customer_edit_id_is_immutable_and_not_supported_by_setter(
    tmp_path: Path,
) -> None:
    controller = _configured_controller(tmp_path).controller

    with pytest.raises(proposal_desktop.DesktopFormError, match="Unsupported"):
        controller.set_customer_edit_field("customer_id", "renamed-customer")

    assert controller.customer_edit_state.customer_id == "customer-synthetic-001"
    source = inspect.getsource(
        proposal_desktop.ProposalDesktopApp._build_customer_edit_section
    )
    assert 'state="readonly" if name == "customer_id" else "normal"' in source


def test_customer_edit_snapshot_clears_on_database_change_and_customer_clear(
    tmp_path: Path,
) -> None:
    controller = _configured_controller(tmp_path).controller
    assert controller.customer_edit_expected_original is not None

    controller.set_text_field("database_path", str(tmp_path / "other.sqlite"))

    assert controller.customer_edit_state == proposal_desktop.CustomerEditState()
    assert controller.customer_edit_expected_original is None


def test_customer_switch_replaces_edit_state_and_snapshot(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    original_snapshot = controller.customer_edit_expected_original

    controller.select_customer("customer-synthetic-002")

    assert controller.customer_edit_expected_original is harness.controller.customers[1]
    assert controller.customer_edit_expected_original is not original_snapshot
    assert controller.customer_edit_state.customer_id == "customer-synthetic-002"
    assert controller.state.selected_job_id == ""


def test_customer_update_record_normalizes_only_explicit_persisted_fields(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    for name, value in {
        "display_name": "  Updated Synthetic Customer  ",
        "phone": "   ",
        "email": " updated@example.invalid ",
        "billing_street_address": " 400 Synthetic Ave. ",
        "billing_city_state_zip": " Example, WI 00000 ",
        "notes": " First updated note\n\n Second updated note ",
    }.items():
        controller.set_customer_edit_field(name, value)

    record = controller.create_customer_update_record()

    assert record == CustomerRecord(
        customer_id="customer-synthetic-001",
        display_name="Updated Synthetic Customer",
        phone=None,
        email="updated@example.invalid",
        billing_street_address="400 Synthetic Ave.",
        billing_city_state_zip="Example, WI 00000",
        notes=["First updated note", "Second updated note"],
    )
    assert harness.customer_update_factory_calls == []
    assert harness.customer_update_calls == []


def test_invalid_customer_edit_performs_no_write(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    harness.controller.set_customer_edit_field("display_name", "   ")

    with pytest.raises(proposal_desktop.DesktopFormError, match="required"):
        harness.controller.update_customer()

    assert harness.customer_update_factory_calls == []
    assert harness.customer_update_calls == []


def test_no_op_customer_save_rejects_before_writable_repository_and_keeps_hash(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "records.sqlite"
    customer_repository = SQLiteCustomerRepository(database_path)
    customer_repository.save_customer(
        CustomerRecord(
            customer_id="customer-synthetic-001",
            display_name="  Synthetic Customer  ",
            phone="  555-0100  ",
            notes=["  Existing explicit note  "],
        )
    )
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))
    controller.load_customers()
    controller.select_customer("customer-synthetic-001")
    hash_before = _database_hash(database_path)

    with pytest.raises(proposal_desktop.NoCustomerChangesError):
        controller.update_customer()

    assert _database_hash(database_path) == hash_before


def test_explicit_customer_update_uses_exact_snapshot_then_reloads_read_only(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    expected_original = controller.customer_edit_expected_original
    read_calls_before = len(harness.customer_factory_calls)
    job_calls_before = len(harness.job_factory_calls)
    controller.set_customer_edit_field("display_name", "Updated Synthetic Customer")
    controller.validate_draft()
    assert controller.generation_enabled is True

    updated = controller.update_customer()

    assert harness.customer_update_factory_calls == [
        (tmp_path / "records.sqlite", False, False)
    ]
    assert len(harness.customer_update_calls) == 1
    assert harness.customer_update_calls[0][0] is updated
    assert harness.customer_update_calls[0][1] is expected_original
    assert len(harness.customer_factory_calls) == read_calls_before + 1
    assert harness.customer_factory_calls[-1] == (
        tmp_path / "records.sqlite",
        False,
        True,
    )
    assert len(harness.job_factory_calls) == job_calls_before + 1
    assert harness.job_factory_calls[-1] == (
        tmp_path / "records.sqlite",
        False,
        True,
    )
    assert controller.state.selected_customer_id == updated.customer_id
    assert controller.state.selected_job_id == ""
    assert controller.customer_edit_expected_original is updated
    assert controller.customer_edit_state.display_name == updated.display_name
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False


@pytest.mark.parametrize(
    ("error", "status_prefix"),
    [
        (
            CustomerNotFoundError(
                "Customer no longer exists; reload customers before retrying."
            ),
            "Customer is missing",
        ),
        (
            CustomerUpdateConflictError(
                "Customer changed elsewhere; reload customers before retrying."
            ),
            "Customer changed elsewhere",
        ),
    ],
)
def test_customer_update_missing_or_stale_is_controlled_without_reload(
    tmp_path: Path,
    error: Exception,
    status_prefix: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    expected_original = controller.customer_edit_expected_original
    controller.set_customer_edit_field("display_name", "Update Attempt")
    read_calls_before = len(harness.customer_factory_calls)
    job_calls_before = len(harness.job_factory_calls)

    class RejectingRepository:
        def update_customer(
            self,
            record: CustomerRecord,
            expected: CustomerRecord,
        ) -> CustomerRecord:
            del record, expected
            raise error

    controller._customer_update_repository_factory = (  # noqa: SLF001
        lambda *_args, **_kwargs: RejectingRepository()
    )
    app_harness = _headless_app(controller)

    app_harness.app._update_customer()

    assert app_harness.customer_edit_status_variable.value.startswith(status_prefix)
    assert len(app_harness.messagebox.errors) == 1
    assert len(harness.customer_factory_calls) == read_calls_before
    assert len(harness.job_factory_calls) == job_calls_before
    assert controller.customer_edit_expected_original is expected_original
    assert controller.state.selected_customer_id == "customer-synthetic-001"
    assert controller.customer_edit_state.display_name == "Update Attempt"
    assert controller.generation_enabled is False


def test_gui_customer_edit_controls_are_explicit_and_typing_never_writes(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    app = app_harness.app
    app._refresh_customer_edit_widgets()

    assert app._customer_edit_variables["customer_id"].value == (
        "customer-synthetic-001"
    )
    assert app._customer_edit_variables["display_name"].value == (
        "Synthetic Customer"
    )
    app._customer_edit_variables["display_name"].set("Updated Synthetic Customer")
    app._on_customer_edit_field_changed("display_name")

    assert harness.customer_update_factory_calls == []
    assert harness.customer_update_calls == []
    assert app_harness.customer_edit_status_variable.value.startswith(
        "Customer edit fields changed"
    )
    source = inspect.getsource(proposal_desktop.ProposalDesktopApp)
    assert 'text="Save Customer Changes"' in source


def test_gui_no_op_customer_save_is_status_only_without_error(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)

    app_harness.app._update_customer()

    assert app_harness.customer_edit_status_variable.value == (
        "No customer changes to save."
    )
    assert app_harness.messagebox.errors == []
    assert harness.customer_update_factory_calls == []


@pytest.mark.parametrize("invalid_state", ["no-selection", "blank-display-name"])
def test_gui_invalid_customer_update_is_controlled_without_write(
    tmp_path: Path,
    invalid_state: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    if invalid_state == "no-selection":
        controller.select_customer("")
    else:
        controller.set_customer_edit_field("display_name", "  ")
    app_harness = _headless_app(controller)

    app_harness.app._update_customer()

    assert app_harness.customer_edit_status_variable.value.startswith(
        "Customer update failed"
    )
    assert len(app_harness.messagebox.errors) == 1
    assert harness.customer_update_factory_calls == []
    assert harness.customer_update_calls == []


def test_gui_customer_update_refreshes_edit_values_and_clears_job_selection(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_customer_edit_field("display_name", "Updated Synthetic Customer")
    app_harness = _headless_app(controller)

    app_harness.app._update_customer()

    assert app_harness.customer_edit_status_variable.value.startswith(
        "Customer updated"
    )
    assert app_harness.customer_combo.current() == 0
    assert app_harness.job_combo.current() == -1
    assert app_harness.app._customer_edit_variables["display_name"].value == (
        "Updated Synthetic Customer"
    )
    assert controller.state.selected_job_id == ""
    assert app_harness.messagebox.errors == []


def test_job_creation_defaults_are_visible_and_have_no_customer_id_field() -> None:
    state = proposal_desktop.JobCreationState()

    assert state.status == JobStatus.draft.value
    assert state.tank_location_type == TankLocationType.unknown.value
    assert state.contents_known is False
    assert "customer_id" not in state.__dataclass_fields__
    source = inspect.getsource(proposal_desktop.ProposalDesktopApp)
    assert 'text="Create Job"' in source


def test_desktop_job_creation_uses_insert_only_primitive_not_legacy_save() -> None:
    source = inspect.getsource(proposal_desktop.ProposalDesktopController.create_job)

    assert ".create_job(record)" in source
    assert ".save_job(" not in source


def test_explicit_job_fields_construct_record_for_selected_loaded_customer(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    for name, value in {
        "status": JobStatus.scheduled.value,
        "tank_location_type": TankLocationType.underground.value,
        "tank_size_gallons": " 1000 ",
        "tank_contents": " synthetic material ",
        "scope_notes": " First explicit scope\n\n Second explicit scope ",
        "internal_notes": " First internal note\n\n Second internal note ",
    }.items():
        controller.set_job_creation_field(name, value)
    controller.set_job_creation_contents_known(True)

    record = controller.create_job_record()

    assert record == JobRecord(
        job_id="job-created-001",
        customer_id="customer-synthetic-001",
        job_name="Created Synthetic Job",
        site_street_address="300 Synthetic Ave.",
        site_city_state_zip="Example, WI 00000",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=1000,
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes=["First explicit scope", "Second explicit scope"],
        internal_notes=["First internal note", "Second internal note"],
    )
    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


def test_blank_optional_job_fields_normalize_without_invented_values(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    for name in (
        "tank_size_gallons",
        "tank_contents",
        "scope_notes",
        "internal_notes",
    ):
        controller.set_job_creation_field(name, "  \n ")

    record = controller.create_job_record()

    assert record.tank_size_gallons is None
    assert record.tank_contents is None
    assert record.scope_notes == []
    assert record.internal_notes == []
    assert record.status == JobStatus.draft
    assert record.tank_location_type == TankLocationType.unknown
    assert record.contents_known is False


@pytest.mark.parametrize(
    "missing_field",
    ["job_id", "job_name", "site_street_address", "site_city_state_zip"],
)
def test_invalid_required_job_data_rejects_before_writable_repository(
    tmp_path: Path,
    missing_field: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    controller.set_job_creation_field(missing_field, "   ")

    with pytest.raises(proposal_desktop.DesktopFormError, match="required"):
        controller.create_job()

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


@pytest.mark.parametrize("tank_size", ["not-an-integer", "0", "-10"])
def test_invalid_tank_size_is_controlled_and_performs_no_write(
    tmp_path: Path,
    tank_size: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    controller.set_job_creation_field("tank_size_gallons", tank_size)

    with pytest.raises(proposal_desktop.DesktopFormError):
        controller.create_job()

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


def test_selected_loaded_customer_is_required_before_job_write(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    controller.select_customer("")

    with pytest.raises(proposal_desktop.DesktopFormError, match="Select an existing"):
        controller.create_job()

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


def test_stale_loaded_customer_is_rejected_before_job_write(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    controller.state.selected_customer_id = "customer-stale"

    with pytest.raises(proposal_desktop.DesktopFormError, match="stale or missing"):
        controller.create_job()

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


def test_customer_disappearing_from_database_is_rejected_before_job_write(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    _set_valid_job_creation_fields(controller)
    customer_read_calls: list[tuple[Path, bool, bool]] = []

    class MissingCustomerRepository:
        def get_customer(self, _customer_id: str) -> None:
            return None

    def missing_customer_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> MissingCustomerRepository:
        customer_read_calls.append((database_path, initialize, read_only))
        return MissingCustomerRepository()

    controller._customer_repository_factory = missing_customer_factory

    with pytest.raises(proposal_desktop.DesktopFormError, match="stale or missing"):
        controller.create_job()

    assert customer_read_calls == [(tmp_path / "records.sqlite", False, True)]
    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []


def test_explicit_job_creation_writes_once_then_reloads_selected_customer_jobs(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    _set_valid_job_creation_fields(controller)
    customer_read_calls_before = len(harness.customer_factory_calls)
    job_read_calls_before = len(harness.job_factory_calls)

    created = controller.create_job()

    database_path = tmp_path / "records.sqlite"
    assert harness.job_creation_factory_calls == [(database_path, False, False)]
    assert harness.job_create_calls == [created]
    assert harness.customer_create_calls == []
    assert len(harness.customer_factory_calls) == customer_read_calls_before + 1
    assert harness.customer_factory_calls[-1] == (database_path, False, True)
    assert len(harness.job_factory_calls) == job_read_calls_before + 1
    assert harness.job_factory_calls[-1] == (database_path, False, True)
    assert harness.job_list_calls[-1] == "customer-synthetic-001"
    assert controller.state.selected_customer_id == "customer-synthetic-001"
    assert controller.state.selected_job_id == ""
    assert controller.jobs[-1] == created
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False


def test_duplicate_job_id_for_other_customer_rejects_without_overwrite_or_reload(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    selected_customer_jobs_before = controller.jobs
    _set_valid_job_creation_fields(controller, job_id="job-synthetic-003")
    job_read_calls_before = len(harness.job_factory_calls)

    with pytest.raises(JobAlreadyExistsError, match="already exists"):
        controller.create_job()

    assert harness.job_creation_factory_calls == [
        (tmp_path / "records.sqlite", False, False)
    ]
    assert harness.job_create_calls == []
    assert len(harness.job_factory_calls) == job_read_calls_before
    assert controller.jobs == selected_customer_jobs_before


def test_job_field_edits_and_customer_selection_do_not_open_writable_job_repo(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller

    _set_valid_job_creation_fields(controller)
    controller.set_job_creation_field("status", JobStatus.proposed.value)
    controller.set_job_creation_field(
        "tank_location_type",
        TankLocationType.aboveground.value,
    )
    controller.set_job_creation_contents_known(True)
    controller.select_customer("customer-synthetic-002")

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []
    assert harness.customer_create_calls == []


def test_job_form_editing_opens_no_repository_until_explicit_create_action(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    app = app_harness.app
    for name, value in {
        "job_id": "job-created-002",
        "job_name": "Created Synthetic Job",
        "site_street_address": "400 Synthetic Ave.",
        "site_city_state_zip": "Example, WI 00000",
    }.items():
        app._job_creation_variables[name].set(value)
        app._on_job_creation_field_changed(name)

    assert harness.job_creation_factory_calls == []
    assert harness.job_create_calls == []
    assert app_harness.job_creation_status_variable.value.startswith(
        "Job details changed"
    )

    app._create_job()

    assert harness.job_creation_factory_calls == [
        (tmp_path / "records.sqlite", False, False)
    ]
    assert len(harness.job_create_calls) == 1
    assert app_harness.job_creation_status_variable.value == (
        "Job job-created-002 created; selected-customer jobs reloaded."
    )
    assert harness.controller.state.selected_customer_id == "customer-synthetic-001"
    assert harness.controller.state.selected_job_id == ""
    assert app_harness.job_combo.current() == -1
    assert app_harness.messagebox.errors == []

    created_index = len(harness.controller.jobs) - 1
    app_harness.job_combo.current(created_index)
    app._on_job_selected()
    assert harness.controller.state.selected_job_id == "job-created-002"


@pytest.mark.parametrize(
    ("selected_customer", "job_id", "expected_status"),
    [
        (False, "job-created-003", "Job creation failed"),
        (True, "", "Job creation failed"),
        (True, "job-synthetic-001", "Duplicate job ID rejected"),
    ],
)
def test_gui_job_creation_failures_are_controlled_and_write_nothing(
    tmp_path: Path,
    selected_customer: bool,
    job_id: str,
    expected_status: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    if not selected_customer:
        controller.select_customer("")
    _set_valid_job_creation_fields(controller, job_id=job_id)
    app_harness = _headless_app(controller)

    app_harness.app._create_job()

    assert app_harness.job_creation_status_variable.value.startswith(expected_status)
    assert len(app_harness.messagebox.errors) == 1
    assert harness.job_create_calls == []


def test_job_selection_populates_edit_state_and_exact_loaded_snapshot(
    tmp_path: Path,
) -> None:
    job = JobRecord(
        job_id="job-synthetic-001",
        customer_id="customer-synthetic-001",
        job_name="Original Synthetic Job",
        site_street_address="100 Synthetic Site",
        site_city_state_zip="Example, WI 00000",
        status=JobStatus.proposed,
        tank_location_type=TankLocationType.aboveground,
        tank_size_gallons=900,
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes=["First scope", "Second scope"],
        internal_notes=["First internal note"],
    )
    harness = _configured_controller(tmp_path, jobs=(job,))
    controller = harness.controller

    assert controller.job_edit_expected_original is job
    assert controller.job_edit_state == proposal_desktop.JobEditState(
        job_id=job.job_id,
        customer_id=job.customer_id,
        job_name=job.job_name,
        site_street_address=job.site_street_address,
        site_city_state_zip=job.site_city_state_zip,
        status=job.status.value,
        tank_location_type=job.tank_location_type.value,
        tank_size_gallons="900",
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes="First scope\nSecond scope",
        internal_notes="First internal note",
    )


def test_desktop_job_update_uses_guarded_primitive_not_legacy_save() -> None:
    source = inspect.getsource(proposal_desktop.ProposalDesktopController.update_job)

    assert ".update_job(record, expected_original)" in source
    assert ".save_job(" not in source


@pytest.mark.parametrize("identity", ["job_id", "customer_id"])
def test_job_edit_identity_fields_are_immutable(identity: str, tmp_path: Path) -> None:
    controller = _configured_controller(tmp_path).controller
    original = controller.job_edit_expected_original

    with pytest.raises(proposal_desktop.DesktopFormError, match="Unsupported"):
        controller.set_job_edit_field(identity, f"changed-{identity}")

    assert controller.job_edit_expected_original is original
    assert getattr(controller.job_edit_state, identity) == getattr(original, identity)
    source = inspect.getsource(proposal_desktop.ProposalDesktopApp._build_job_edit_section)
    assert 'name in {"job_id", "customer_id"}' in source


def test_job_edit_snapshot_clears_and_switches_with_selection_lifecycle(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    first_snapshot = controller.job_edit_expected_original

    controller.select_job("")
    assert controller.job_edit_expected_original is None
    assert controller.job_edit_state == proposal_desktop.JobEditState()

    controller.select_job("job-synthetic-002")
    assert controller.job_edit_expected_original is harness.controller.jobs[1]
    assert controller.job_edit_expected_original is not first_snapshot

    controller.select_customer("customer-synthetic-002")
    assert controller.job_edit_expected_original is None
    assert controller.job_edit_state == proposal_desktop.JobEditState()

    controller.set_text_field("database_path", str(tmp_path / "other.sqlite"))
    assert controller.job_edit_expected_original is None


def test_job_update_record_uses_immutable_identity_and_normalizes_explicit_fields(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    for name, value in {
        "job_name": " Updated Synthetic Job ",
        "site_street_address": " 700 Synthetic Site ",
        "site_city_state_zip": " Example, WI 00000 ",
        "status": JobStatus.scheduled.value,
        "tank_location_type": TankLocationType.underground.value,
        "tank_size_gallons": " 1200 ",
        "tank_contents": " synthetic material ",
        "scope_notes": " First updated scope\n\n Second updated scope ",
        "internal_notes": " First internal note\n\n Second internal note ",
    }.items():
        controller.set_job_edit_field(name, value)
    controller.set_job_edit_contents_known(True)

    record = controller.create_job_update_record()

    assert record == JobRecord(
        job_id="job-synthetic-001",
        customer_id="customer-synthetic-001",
        job_name="Updated Synthetic Job",
        site_street_address="700 Synthetic Site",
        site_city_state_zip="Example, WI 00000",
        status=JobStatus.scheduled,
        tank_location_type=TankLocationType.underground,
        tank_size_gallons=1200,
        tank_contents="synthetic material",
        contents_known=True,
        scope_notes=["First updated scope", "Second updated scope"],
        internal_notes=["First internal note", "Second internal note"],
    )
    assert harness.job_update_factory_calls == []
    assert harness.job_update_calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_name", "   "),
        ("site_street_address", "   "),
        ("site_city_state_zip", "   "),
        ("tank_size_gallons", "not-an-integer"),
        ("tank_size_gallons", "0"),
        ("status", "not-a-status"),
        ("tank_location_type", "not-a-location"),
    ],
)
def test_invalid_job_edit_rejects_before_writable_repository(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    harness = _configured_controller(tmp_path)
    harness.controller.set_job_edit_field(field, value)

    with pytest.raises(proposal_desktop.DesktopFormError):
        harness.controller.update_job()

    assert harness.job_update_factory_calls == []
    assert harness.job_update_calls == []


def test_no_op_job_save_rejects_without_write_and_keeps_hash(tmp_path: Path) -> None:
    database_path = tmp_path / "records.sqlite"
    SQLiteCustomerRepository(database_path).save_customer(_customer())
    job = JobRecord(
        job_id="job-synthetic-001",
        customer_id="customer-synthetic-001",
        job_name="  Synthetic Job  ",
        site_street_address=" 100 Synthetic Site ",
        site_city_state_zip=" Example, WI 00000 ",
        tank_contents=" synthetic material ",
        scope_notes=[" Explicit scope "],
    )
    SQLiteJobRepository(database_path, initialize=False).save_job(job)
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))
    controller.load_customers()
    controller.select_customer("customer-synthetic-001")
    controller.select_job("job-synthetic-001")
    hash_before = _database_hash(database_path)

    with pytest.raises(proposal_desktop.NoJobChangesError):
        controller.update_job()

    assert _database_hash(database_path) == hash_before


def test_explicit_job_update_uses_exact_snapshot_then_reloads_and_reselects(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    expected_original = controller.job_edit_expected_original
    customer_read_calls_before = len(harness.customer_factory_calls)
    job_read_calls_before = len(harness.job_factory_calls)
    controller.set_job_edit_field("job_name", "Updated Synthetic Job")
    controller.validate_draft()
    assert controller.generation_enabled is True

    updated = controller.update_job()

    database_path = tmp_path / "records.sqlite"
    assert harness.job_update_factory_calls == [(database_path, False, False)]
    assert len(harness.job_update_calls) == 1
    assert harness.job_update_calls[0][0] is updated
    assert harness.job_update_calls[0][1] is expected_original
    assert len(harness.customer_factory_calls) == customer_read_calls_before + 1
    assert harness.customer_factory_calls[-1] == (database_path, False, True)
    assert len(harness.job_factory_calls) == job_read_calls_before + 1
    assert harness.job_factory_calls[-1] == (database_path, False, True)
    assert controller.state.selected_customer_id == updated.customer_id
    assert controller.state.selected_job_id == updated.job_id
    assert controller.job_edit_expected_original is updated
    assert controller.job_edit_state.job_name == updated.job_name
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False


def test_stale_customer_rejects_before_writable_job_repository(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_job_edit_field("job_name", "Update Attempt")
    customer_read_calls: list[tuple[Path, bool, bool]] = []

    class MissingCustomerRepository:
        def get_customer(self, _customer_id: str) -> None:
            return None

    def missing_customer_factory(
        database_path: Path,
        *,
        initialize: bool,
        read_only: bool,
    ) -> MissingCustomerRepository:
        customer_read_calls.append((database_path, initialize, read_only))
        return MissingCustomerRepository()

    controller._customer_repository_factory = missing_customer_factory

    with pytest.raises(proposal_desktop.DesktopFormError, match="stale or missing"):
        controller.update_job()

    assert customer_read_calls == [(tmp_path / "records.sqlite", False, True)]
    assert harness.job_update_factory_calls == []
    assert harness.job_update_calls == []


@pytest.mark.parametrize(
    ("error", "status_prefix"),
    [
        (
            JobNotFoundError("Job no longer exists; reload jobs before retrying."),
            "Job is missing",
        ),
        (
            JobUpdateConflictError(
                "Job changed elsewhere; reload jobs before retrying."
            ),
            "Job changed elsewhere",
        ),
    ],
)
def test_job_update_missing_or_stale_is_controlled_without_reload(
    tmp_path: Path,
    error: Exception,
    status_prefix: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    expected_original = controller.job_edit_expected_original
    controller.set_job_edit_field("job_name", "Update Attempt")
    job_read_calls_before = len(harness.job_factory_calls)

    class RejectingRepository:
        def update_job(
            self,
            record: JobRecord,
            expected: JobRecord,
        ) -> JobRecord:
            del record, expected
            raise error

    controller._job_update_repository_factory = (  # noqa: SLF001
        lambda *_args, **_kwargs: RejectingRepository()
    )
    app_harness = _headless_app(controller)

    app_harness.app._update_job()

    assert app_harness.job_edit_status_variable.value.startswith(status_prefix)
    assert len(app_harness.messagebox.errors) == 1
    assert len(harness.job_factory_calls) == job_read_calls_before
    assert controller.job_edit_expected_original is expected_original
    assert controller.state.selected_job_id == "job-synthetic-001"
    assert controller.job_edit_state.job_name == "Update Attempt"
    assert controller.generation_enabled is False


def test_gui_job_edit_controls_are_explicit_and_typing_never_writes(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    app = app_harness.app
    app._refresh_job_edit_widgets()

    assert app._job_edit_variables["job_id"].value == "job-synthetic-001"
    assert app._job_edit_variables["customer_id"].value == (
        "customer-synthetic-001"
    )
    app._job_edit_variables["job_name"].set("Updated Synthetic Job")
    app._on_job_edit_field_changed("job_name")

    assert harness.job_update_factory_calls == []
    assert harness.job_update_calls == []
    assert app_harness.job_edit_status_variable.value.startswith(
        "Job edit fields changed"
    )
    source = inspect.getsource(proposal_desktop.ProposalDesktopApp)
    assert 'text="Save Job Changes"' in source


def test_gui_no_op_and_invalid_job_saves_are_controlled(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)

    app_harness.app._update_job()

    assert app_harness.job_edit_status_variable.value == "No job changes to save."
    assert app_harness.messagebox.errors == []
    assert harness.job_update_factory_calls == []

    harness.controller.select_job("")
    app_harness.app._update_job()
    assert app_harness.job_edit_status_variable.value.startswith("Job update failed")
    assert len(app_harness.messagebox.errors) == 1
    assert harness.job_update_factory_calls == []


def test_gui_job_update_refreshes_values_and_preserves_association(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_job_edit_field("job_name", "Updated Synthetic Job")
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(0)

    app_harness.app._update_job()

    assert app_harness.job_edit_status_variable.value.startswith("Job updated")
    assert app_harness.customer_combo.current() == 0
    assert app_harness.job_combo.current() == 0
    assert app_harness.app._job_edit_variables["job_name"].value == (
        "Updated Synthetic Job"
    )
    assert controller.state.selected_customer_id == "customer-synthetic-001"
    assert controller.state.selected_job_id == "job-synthetic-001"
    assert controller.job_edit_expected_original is harness.job_update_calls[0][0]
    assert app_harness.messagebox.errors == []


def test_output_proposal_is_identity_free_and_creates_nothing(tmp_path: Path) -> None:
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    output_root = tmp_path / "private-output"
    sensitive_values = (
        "Synthetic Customer",
        "customer-synthetic-001",
        "Synthetic Tank Project",
        "job-synthetic-001",
        "100 Example Ave",
        "Explicit synthetic work",
        "125.00",
        "Synthetic Services",
    )

    output_folder, output_json, output_docx = controller.propose_output_paths(output_root)

    assert output_folder == output_root / "proposal-draft-20260730-140506"
    assert output_json == output_folder / "proposal_input.json"
    assert output_docx == output_folder / "proposal.docx"
    combined = "|".join((str(output_folder), str(output_json), str(output_docx)))
    assert all(value not in combined for value in sensitive_values)
    assert not output_root.exists()
    assert not output_folder.exists()
    assert not output_json.exists()
    assert not output_docx.exists()


def test_explicit_docx_selection_defaults_extension_and_configures_pipeline_paths(
    tmp_path: Path,
) -> None:
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    selected = tmp_path / "private-output" / "explicit-proposal"

    output_folder, output_json, output_docx = controller.select_docx_output_path(
        selected
    )

    assert output_folder == selected.parent
    assert output_json == selected.parent / "proposal_input.json"
    assert output_docx == selected.with_suffix(".docx")
    assert controller.state.output_root == str(output_folder)
    assert controller.state.output_folder == str(output_folder)
    assert controller.state.proposal_input_json_output_path == str(output_json)
    assert controller.state.proposal_docx_output_path == str(output_docx)
    assert not output_folder.exists()
    assert not output_json.exists()
    assert not output_docx.exists()


def test_explicit_docx_selection_rejects_other_extensions(tmp_path: Path) -> None:
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    original = controller.snapshot()

    with pytest.raises(proposal_desktop.DesktopFormError, match=r"\.docx extension"):
        controller.select_docx_output_path(tmp_path / "proposal.pdf")

    assert controller.snapshot() == original


def test_existing_docx_overwrite_is_rejected_without_changing_file_or_state(
    tmp_path: Path,
) -> None:
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    existing = tmp_path / "private-output" / "proposal.docx"
    existing.parent.mkdir()
    original_bytes = b"existing synthetic document bytes"
    existing.write_bytes(original_bytes)
    original = controller.snapshot()

    with pytest.raises(
        proposal_desktop.ExistingOutputPathError,
        match="overwrite was rejected",
    ):
        controller.select_docx_output_path(existing)

    assert existing.read_bytes() == original_bytes
    assert controller.snapshot() == original
    assert controller.build_result is None


def test_docx_save_dialog_cancellation_is_a_no_op_and_creates_nothing(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    before = harness.controller.snapshot()
    app_harness.filedialog.save_result = ""

    app_harness.app._browse_docx_output()

    assert harness.controller.snapshot() == before
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert not Path(harness.controller.state.output_folder).exists()
    assert app_harness.status_variable.value == (
        "Output selection cancelled; no file was created."
    )
    assert app_harness.messagebox.errors == []


def test_docx_save_dialog_uses_safe_defaults_and_updates_explicit_paths(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    selected = tmp_path / "chosen-output" / "controlled-proposal.docx"
    app_harness.filedialog.save_result = str(selected)

    app_harness.app._browse_docx_output()

    assert len(app_harness.filedialog.save_calls) == 1
    options = app_harness.filedialog.save_calls[0]
    assert options["defaultextension"] == ".docx"
    assert options["confirmoverwrite"] is True
    assert options["filetypes"] == (("Word document", "*.docx"),)
    assert harness.controller.state.output_root == str(selected.parent)
    assert harness.controller.state.output_folder == str(selected.parent)
    assert harness.controller.state.proposal_input_json_output_path == str(
        selected.parent / "proposal_input.json"
    )
    assert harness.controller.state.proposal_docx_output_path == str(selected)
    assert app_harness.generate_button.state == "disabled"
    assert app_harness.status_variable.value.startswith("DOCX output selected")
    assert harness.build_calls == []
    assert not selected.parent.exists()


def test_docx_save_dialog_reports_overwrite_rejection_without_generation(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    app_harness = _headless_app(harness.controller)
    existing = tmp_path / "existing.docx"
    original_bytes = b"existing synthetic document bytes"
    existing.write_bytes(original_bytes)
    app_harness.filedialog.save_result = str(existing)

    app_harness.app._browse_docx_output()

    assert existing.read_bytes() == original_bytes
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert app_harness.status_variable.value.startswith("Overwrite rejected")
    assert len(app_harness.messagebox.errors) == 1
    assert "overwrite was rejected" in app_harness.messagebox.errors[0][1]


def test_git_worktree_detection_recognizes_dot_git_directory(tmp_path: Path) -> None:
    worktree = tmp_path / "repository"
    (worktree / ".git").mkdir(parents=True)

    assert proposal_desktop.is_path_inside_git_worktree(
        worktree / "private" / "proposal.docx"
    )


def test_git_worktree_detection_recognizes_dot_git_file(tmp_path: Path) -> None:
    worktree = tmp_path / "linked-worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: ../metadata", encoding="utf-8")

    assert proposal_desktop.is_path_inside_git_worktree(
        worktree / "private" / "proposal.docx"
    )


def test_git_worktree_detection_checks_only_selected_ancestors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "selected" / "private" / "proposal.docx"
    unrelated = tmp_path / "unrelated"
    (unrelated / ".git").mkdir(parents=True)

    def recursive_scan_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("recursive filesystem scanning is forbidden")

    monkeypatch.setattr(Path, "rglob", recursive_scan_forbidden)

    assert proposal_desktop.is_path_inside_git_worktree(selected) is False


def test_records_database_inside_git_worktree_is_rejected_before_loading(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    worktree = tmp_path / "repository"
    (worktree / ".git").mkdir(parents=True)
    harness.controller.set_text_field(
        "database_path",
        str(worktree / "private" / "records.sqlite"),
    )

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="outside every Git worktree",
    ):
        harness.controller.load_customers()


@pytest.mark.parametrize(
    "field_name",
    [
        "template_path",
        "output_root",
        "output_folder",
        "proposal_input_json_output_path",
        "proposal_docx_output_path",
    ],
)
def test_selected_template_and_output_targets_inside_git_worktree_are_rejected(
    tmp_path: Path,
    field_name: str,
) -> None:
    harness = _configured_controller(tmp_path)
    worktree = tmp_path / "repository"
    (worktree / ".git").mkdir(parents=True)
    suffix = ".docx" if field_name in {"template_path", "proposal_docx_output_path"} else ""
    target = worktree / "private" / f"{field_name}{suffix}"
    harness.controller.set_text_field(field_name, str(target))

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="outside every Git worktree",
    ):
        harness.controller.validate_draft()


def test_customer_repository_is_non_initializing_read_only_and_selects_nothing(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.load_customers()

    assert harness.customer_factory_calls[-1] == (
        tmp_path / "records.sqlite",
        False,
        True,
    )
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.customer_display_labels == (
        "Synthetic Customer [customer-synthetic-001]",
        "Synthetic Customer [customer-synthetic-002]",
    )


def test_customer_selection_loads_only_its_jobs_without_auto_selection(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.select_customer("customer-synthetic-001")

    assert harness.job_factory_calls[-1] == (
        tmp_path / "records.sqlite",
        False,
        True,
    )
    assert harness.job_list_calls[-1] == "customer-synthetic-001"
    assert [job.job_id for job in controller.jobs] == [
        "job-synthetic-001",
        "job-synthetic-002",
    ]
    assert controller.state.selected_job_id == ""
    assert controller.job_display_labels == (
        "Synthetic Tank Project [job-synthetic-001]",
        "Synthetic Inspection [job-synthetic-002]",
    )


def test_changing_customer_clears_job_selection_and_list_is_relationship_scoped(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    assert controller.state.selected_job_id == "job-synthetic-001"

    controller.select_customer("customer-synthetic-002")

    assert controller.state.selected_customer_id == "customer-synthetic-002"
    assert controller.state.selected_job_id == ""
    assert [job.job_id for job in controller.jobs] == ["job-synthetic-003"]


def test_mismatched_job_returned_by_repository_fails_closed(tmp_path: Path) -> None:
    customer = _customer()
    mismatched_job = _job(customer_id="customer-other")

    class CustomerRepository:
        def list_customers(self) -> list[CustomerRecord]:
            return [customer]

    class JobRepository:
        def list_jobs_for_customer(self, _customer_id: str) -> list[JobRecord]:
            return [mismatched_job]

    controller = proposal_desktop.ProposalDesktopController(
        customer_repository_factory=lambda *_args, **_kwargs: CustomerRepository(),
        job_repository_factory=lambda *_args, **_kwargs: JobRepository(),
        clock=lambda: NOW,
    )
    controller.set_text_field("database_path", str(tmp_path / "records.sqlite"))
    controller.load_customers()

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="does not belong",
    ):
        controller.select_customer(customer.customer_id)


@pytest.mark.parametrize("missing_selection", ["customer", "job", "stale-job"])
def test_missing_or_stale_explicit_selections_block_validation(
    tmp_path: Path,
    missing_selection: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    if missing_selection == "customer":
        controller.load_customers()
    elif missing_selection == "job":
        controller.select_customer("customer-synthetic-001")
    else:
        with pytest.raises(proposal_desktop.DesktopFormError, match="loaded for the customer"):
            controller.select_job("job-stale")
        return

    with pytest.raises(proposal_desktop.DesktopFormError, match="Select an existing"):
        controller.validate_draft()
    assert harness.validation_calls == []


def test_real_sqlite_selection_uses_immutable_non_initializing_reads(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "records.sqlite"
    _seed_database(database_path)
    before = _database_hash(database_path)
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))

    customers = controller.load_customers()
    jobs = controller.select_customer("customer-synthetic-001")

    assert customers == (_customer(),)
    assert jobs == (_job(),)
    assert _database_hash(database_path) == before
    assert not Path(f"{database_path}-wal").exists()
    assert not Path(f"{database_path}-shm").exists()
    assert not Path(f"{database_path}-journal").exists()


def test_loading_missing_database_does_not_initialize_it(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite"
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))

    with pytest.raises(Exception):
        controller.load_customers()

    assert not database_path.exists()
    assert not database_path.parent.joinpath("missing.sqlite-wal").exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sqlite_sidecars_fail_closed_and_remain_untouched(
    tmp_path: Path,
    suffix: str,
) -> None:
    database_path = tmp_path / "records.sqlite"
    _seed_database(database_path)
    before = _database_hash(database_path)
    sidecar = Path(f"{database_path}{suffix}")
    sidecar.write_bytes(b"synthetic-existing-sidecar")
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))

    with pytest.raises(Exception):
        controller.load_customers()

    assert _database_hash(database_path) == before
    assert sidecar.read_bytes() == b"synthetic-existing-sidecar"


def test_scope_items_are_explicit_and_sequential_after_add_remove_and_reorder(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_scope_description(0, "First explicit scope")
    controller.set_scope_description(1, "Second explicit scope")
    third = controller.add_scope_item("Third explicit scope")
    controller.move_scope_item(third, -1)
    controller.remove_scope_item(2)

    assert controller.numbered_scope_items() == (
        (1, "First explicit scope"),
        (2, "Third explicit scope"),
    )
    assert [
        (item.number, item.description)
        for item in controller.create_details().scope_items
    ] == [
        (1, "First explicit scope"),
        (2, "Third explicit scope"),
    ]


@pytest.mark.parametrize(
    "scope_descriptions",
    [
        [],
        [""],
        ["   "],
        ["Explicit scope", ""],
    ],
)
def test_scope_requires_every_row_and_at_least_one_non_empty_description(
    tmp_path: Path,
    scope_descriptions: list[str],
) -> None:
    harness = _configured_controller(tmp_path)
    harness.controller.state.scope_descriptions = scope_descriptions

    with pytest.raises(proposal_desktop.DesktopFormError, match="scope item"):
        harness.controller.create_details()


def test_explicit_fields_construct_expected_record_proposal_details(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_text_field("proposal_date", "2026-08-01")
    controller.set_text_field("item_description", "Explicit item wording")
    controller.set_scope_description(0, "Explicit first scope")
    controller.set_scope_description(1, "Explicit second scope")
    controller.set_text_field("amount", "417.25")
    controller.set_starting_at(True)
    controller.set_text_field("pricing_note", "Explicit pricing qualification")
    controller.set_text_field("notes", "Keep this wording\n\nAnd this wording")
    controller.set_text_field("company_name", "Synthetic Services")
    controller.set_text_field("terms_and_conditions", "Explicit payment terms")
    controller.set_text_field("starting_at_label", "Starting at")
    controller.set_text_field("total_label", "TOTAL")

    details = controller.create_details()

    assert details.proposal_date.isoformat() == "2026-08-01"
    assert details.item_description == "Explicit item wording"
    assert [(item.number, item.description) for item in details.scope_items] == [
        (1, "Explicit first scope"),
        (2, "Explicit second scope"),
    ]
    assert details.pricing.amount == Decimal("417.25")
    assert details.pricing.is_starting_at is True
    assert details.pricing.pricing_note == "Explicit pricing qualification"
    assert details.notes == ["Keep this wording", "And this wording"]
    assert details.company_config.company_name == "Synthetic Services"
    assert details.company_config.terms_and_conditions == "Explicit payment terms"
    assert details.company_config.starting_at_label == "Starting at"
    assert details.company_config.total_label == "TOTAL"


def test_empty_optional_pricing_note_and_terms_become_none(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_text_field("pricing_note", "  ")
    controller.set_text_field("terms_and_conditions", "\n")

    details = controller.create_details()

    assert details.pricing.pricing_note is None
    assert details.company_config.terms_and_conditions is None


def test_validation_constructs_one_request_and_calls_validation_once(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)

    result = harness.controller.validate_draft()

    assert len(harness.validation_calls) == 1
    assert harness.build_calls == []
    request = harness.validation_calls[0]
    assert isinstance(request, ProposalDraftBuildRequest)
    assert request.customer_id == "customer-synthetic-001"
    assert request.job_id == "job-synthetic-001"
    assert request.details.item_description == "Explicit synthetic work"
    assert request.proposal_input_json_output_path.name == "proposal_input.json"
    assert request.proposal_docx_output_path.name == "proposal.docx"
    assert harness.controller.validated_request is request
    assert harness.controller.validation_summary_lines == result.summary_lines
    assert harness.controller.generation_enabled is True
    assert harness.controller.open_actions_enabled is False


def test_real_validation_creates_no_outputs_or_directories_and_logs_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    controller = _configure_real_validation_controller(tmp_path, monkeypatch)
    database_path = Path(controller.state.database_path)
    before = _database_hash(database_path)
    output_folder = Path(controller.state.output_folder)

    result = controller.validate_draft()
    captured = capsys.readouterr()

    assert result.proposal.customer_name == "Synthetic Customer"
    assert not output_folder.exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()
    assert list(tmp_path.rglob("*.tmp")) == []
    assert _database_hash(database_path) == before
    assert captured.out == ""
    assert captured.err == ""


def test_real_explicit_docx_selection_generates_through_existing_pipeline(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "records.sqlite"
    _seed_database(database_path)
    template_path = tmp_path / "template.docx"
    shutil.copyfile(TEMPLATE, template_path)
    output_docx = tmp_path / "selected-output" / "controlled-proposal.docx"
    controller = proposal_desktop.ProposalDesktopController(clock=lambda: NOW)
    controller.set_text_field("database_path", str(database_path))
    controller.set_text_field("template_path", str(template_path))
    controller.select_docx_output_path(output_docx)
    controller.set_text_field("item_description", "Explicit synthetic work")
    controller.set_scope_description(0, "Perform explicit synthetic task")
    controller.set_text_field("amount", "125.00")
    controller.set_text_field("company_name", "Synthetic Services")
    controller.load_customers()
    controller.select_customer("customer-synthetic-001")
    controller.select_job("job-synthetic-001")
    database_before = _database_hash(database_path)

    controller.validate_draft()
    result = controller.generate_draft()

    assert result.proposal_docx_path == output_docx
    assert result.proposal_input_json_path == output_docx.parent / "proposal_input.json"
    assert result.proposal_docx_path.is_file()
    assert result.proposal_docx_path.stat().st_size > 0
    assert result.proposal_input_json_path.is_file()
    assert _database_hash(database_path) == database_before


@pytest.mark.parametrize(
    "change",
    [
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
        "is_starting_at",
        "scope_description",
        "scope_add",
        "scope_remove",
        "scope_reorder",
        "customer",
        "job",
    ],
)
def test_every_relevant_change_immediately_invalidates_successful_validation(
    tmp_path: Path,
    change: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    assert controller.generation_enabled is True

    if change in {
        "database_path",
        "template_path",
        "output_root",
        "output_folder",
        "proposal_input_json_output_path",
        "proposal_docx_output_path",
    }:
        controller.set_text_field(change, str(tmp_path / f"changed-{change}"))
    elif change == "proposal_date":
        controller.set_text_field(change, "2026-08-02")
    elif change in {
        "item_description",
        "amount",
        "pricing_note",
        "notes",
        "company_name",
        "terms_and_conditions",
        "starting_at_label",
        "total_label",
    }:
        controller.set_text_field(change, f"changed {change}")
    elif change == "is_starting_at":
        controller.set_starting_at(True)
    elif change == "scope_description":
        controller.set_scope_description(0, "Changed explicit scope")
    elif change == "scope_add":
        controller.add_scope_item("Added explicit scope")
    elif change == "scope_remove":
        controller.remove_scope_item(1)
    elif change == "scope_reorder":
        controller.move_scope_item(0, 1)
    elif change == "customer":
        controller.select_customer("customer-synthetic-002")
    else:
        controller.select_job("job-synthetic-002")

    assert controller.generation_enabled is False
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.validation_summary_lines == ()
    assert controller.open_actions_enabled is False


def test_generation_requires_validation_and_rejects_dirty_state(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller

    with pytest.raises(proposal_desktop.DesktopFormError, match="Validate"):
        controller.generate_draft()

    controller.validate_draft()
    controller.set_text_field("notes", "Changed after validation")

    with pytest.raises(proposal_desktop.DesktopFormError, match="Validate"):
        controller.generate_draft()
    assert harness.build_calls == []


def test_generation_passes_exact_stored_request_to_build_once(tmp_path: Path) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    validated_request = controller.validated_request

    result = controller.generate_draft()

    assert harness.validation_calls == [validated_request]
    assert harness.build_calls == [validated_request]
    assert harness.build_calls[0] is validated_request
    assert controller.build_result is result
    assert controller.open_actions_enabled is True
    assert harness.opened_paths == []


def test_open_actions_are_disabled_before_build_and_open_only_generated_paths(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    for action in (
        controller.open_proposal_input_json,
        controller.open_proposal_docx,
        controller.open_output_folder,
    ):
        with pytest.raises(proposal_desktop.DesktopFormError, match="Generate"):
            action()
    assert harness.opened_paths == []

    controller.validate_draft()
    result = controller.generate_draft()
    controller.open_proposal_input_json()
    controller.open_proposal_docx()
    controller.open_output_folder()

    assert harness.opened_paths == [
        result.proposal_input_json_path,
        result.proposal_docx_path,
        result.proposal_input_json_path.parent,
    ]


def test_failed_revalidation_clears_prior_request_summary_and_generation_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()
    failed_attempts: list[ProposalDraftBuildRequest] = []

    def fail_validation(request: ProposalDraftBuildRequest) -> ProposalDraftValidationResult:
        failed_attempts.append(request)
        raise proposal_desktop.DesktopFormError("Synthetic validation failure")

    controller._validation_function = fail_validation

    with pytest.raises(proposal_desktop.DesktopFormError, match="Synthetic validation"):
        controller.validate_draft()

    assert len(failed_attempts) == 1
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert controller.validation_summary_lines == ()
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []


def test_failed_request_construction_clears_prior_validation_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()
    controller.state.amount = "not-a-decimal"

    with pytest.raises(proposal_desktop.DesktopFormError, match="valid ISO"):
        controller.validate_draft()

    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert controller.validation_summary_lines == ()
    assert len(harness.validation_calls) == 1
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []


def test_failed_customer_reload_clears_loaded_records_selections_and_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()

    def fail_customer_repository(*_args: object, **_kwargs: object) -> Any:
        raise OSError("Synthetic immutable customer read failure")

    controller._customer_repository_factory = fail_customer_repository

    with pytest.raises(OSError, match="Synthetic immutable"):
        controller.load_customers()

    assert controller.customers == ()
    assert controller.jobs == ()
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.validation_summary_lines == ()
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []
    assert controller.customer_edit_state == proposal_desktop.CustomerEditState()
    assert controller.customer_edit_expected_original is None


def test_failed_customer_transition_clears_selections_jobs_and_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()

    class FailingJobRepository:
        def list_jobs_for_customer(self, _customer_id: str) -> list[JobRecord]:
            raise OSError("Synthetic immutable job read failure")

    controller._job_repository_factory = (
        lambda *_args, **_kwargs: FailingJobRepository()
    )

    with pytest.raises(OSError, match="Synthetic immutable"):
        controller.select_customer("customer-synthetic-002")

    assert len(controller.customers) == 2
    assert controller.jobs == ()
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.validation_summary_lines == ()
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []
    assert controller.customer_edit_state == proposal_desktop.CustomerEditState()
    assert controller.customer_edit_expected_original is None


def test_failed_job_selection_leaves_job_blank_and_generation_disabled(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()

    with pytest.raises(proposal_desktop.DesktopFormError, match="loaded for the customer"):
        controller.select_job("job-stale")

    assert controller.state.selected_customer_id == "customer-synthetic-001"
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []


def test_failed_rebuild_clears_prior_result_but_preserves_unchanged_validation(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()
    validated_request = controller.validated_request
    validated_resolved_paths = controller._validated_resolved_paths
    failed_attempts: list[ProposalDraftBuildRequest] = []

    def fail_build(request: ProposalDraftBuildRequest) -> ProposalDraftBuildResult:
        failed_attempts.append(request)
        raise proposal_desktop.DesktopFormError("Synthetic build failure")

    controller._build_function = fail_build

    with pytest.raises(proposal_desktop.DesktopFormError, match="Synthetic build"):
        controller.generate_draft()

    assert failed_attempts == [validated_request]
    assert failed_attempts[0] is validated_request
    assert controller.validated_request is validated_request
    assert controller._validated_resolved_paths is validated_resolved_paths
    assert controller.generation_enabled is True
    assert controller.build_result is None
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []


@pytest.mark.parametrize(
    ("label", "state_field"),
    [
        ("Records Database", "database_path"),
        ("DOCX Template", "template_path"),
        ("Output Root", "output_root"),
        ("Output Folder", "output_folder"),
        ("Proposal Input JSON", "proposal_input_json_output_path"),
        ("Proposal DOCX", "proposal_docx_output_path"),
    ],
)
def test_pre_build_worktree_recheck_covers_every_selected_path_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    state_field: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    blocked_path = Path(getattr(controller.state, state_field)).resolve(strict=False)
    checked_paths: list[Path] = []

    def detect_selected_worktree(path: Path) -> tuple[Path, bool]:
        resolved = path.resolve(strict=False)
        checked_paths.append(resolved)
        return resolved, resolved == blocked_path

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        detect_selected_worktree,
    )

    with pytest.raises(proposal_desktop.DesktopFormError, match=label):
        controller.generate_draft()

    assert blocked_path in checked_paths
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()


def test_stable_private_paths_are_all_rechecked_before_exact_request_is_built(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    validated_request = controller.validated_request
    checked_paths: list[Path] = []

    def record_private_path(path: Path) -> tuple[Path, bool]:
        checked_paths.append(path)
        return path.resolve(strict=False), False

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        record_private_path,
    )

    controller.generate_draft()

    assert checked_paths == [
        Path(controller.state.database_path),
        Path(controller.state.template_path),
        Path(controller.state.output_root),
        Path(controller.state.output_folder),
        Path(controller.state.proposal_input_json_output_path),
        Path(controller.state.proposal_docx_output_path),
    ]
    assert harness.build_calls == [validated_request]
    assert harness.build_calls[0] is validated_request


def test_validation_captures_all_resolved_paths_before_and_after_one_service_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry
    original_validation = controller._validation_function
    events: list[str] = []
    inspected_paths: list[Path] = []

    def inspect_path(path: Path) -> tuple[Path, bool]:
        events.append("path")
        inspected_paths.append(path)
        return original_inspect(path)

    def validate_once(
        request: ProposalDraftBuildRequest,
    ) -> ProposalDraftValidationResult:
        events.append("validation")
        return original_validation(request)

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        inspect_path,
    )
    controller._validation_function = validate_once

    controller.validate_draft()

    selected_paths = list(controller._selected_paths().values())
    assert events == ["path"] * 6 + ["validation"] + ["path"] * 6
    assert inspected_paths == selected_paths + selected_paths
    assert len(harness.validation_calls) == 1
    resolved_paths = controller._validated_resolved_paths
    assert resolved_paths is not None
    assert tuple(label for label, _ in resolved_paths.labeled_paths()) == (
        "Records Database",
        "DOCX Template",
        "Output Root",
        "Output Folder",
        "Proposal Input JSON",
        "Proposal DOCX",
    )
    assert tuple(path for _, path in resolved_paths.labeled_paths()) == tuple(
        path.resolve(strict=False) for path in selected_paths
    )


def test_resolved_path_change_during_validation_discards_result_and_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry
    template_path = Path(controller.state.template_path)
    template_inspections = 0

    def retarget_during_validation(path: Path) -> tuple[Path, bool]:
        nonlocal template_inspections
        resolved, inside_worktree = original_inspect(path)
        if path == template_path:
            template_inspections += 1
            if template_inspections == 2:
                return resolved.with_name("retargeted-template.docx"), False
        return resolved, inside_worktree

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        retarget_during_validation,
    )

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="DOCX Template resolved location changed",
    ):
        controller.validate_draft()

    assert len(harness.validation_calls) == 1
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []


def test_metadata_failure_after_validation_service_discards_returned_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry
    original_validation = controller._validation_function
    validation_returned = False
    template_path = Path(controller.state.template_path)

    def validate_once(
        request: ProposalDraftBuildRequest,
    ) -> ProposalDraftValidationResult:
        nonlocal validation_returned
        result = original_validation(request)
        validation_returned = True
        return result

    def fail_after_validation(path: Path) -> tuple[Path, bool]:
        if validation_returned and path == template_path:
            raise OSError("synthetic post-validation metadata failure")
        return original_inspect(path)

    controller._validation_function = validate_once
    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        fail_after_validation,
    )

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="DOCX Template ancestry could not be verified",
    ):
        controller.validate_draft()

    assert validation_returned is True
    assert len(harness.validation_calls) == 1
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []


@pytest.mark.parametrize(
    ("label", "state_field"),
    [
        ("Records Database", "database_path"),
        ("DOCX Template", "template_path"),
        ("Output Root", "output_root"),
        ("Output Folder", "output_folder"),
        ("Proposal Input JSON", "proposal_input_json_output_path"),
        ("Proposal DOCX", "proposal_docx_output_path"),
    ],
)
def test_cross_platform_resolved_path_mismatch_revokes_all_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    state_field: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry
    selected_path = Path(getattr(controller.state, state_field))

    def retarget_selected_path(path: Path) -> tuple[Path, bool]:
        resolved, inside_worktree = original_inspect(path)
        if path == selected_path:
            return resolved.with_name(f"retargeted-{resolved.name}"), False
        return resolved, inside_worktree

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        retarget_selected_path,
    )

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match=rf"{label} resolved location changed",
    ):
        controller.generate_draft()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()


def test_selected_path_metadata_errors_propagate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = tmp_path / "selected-private-file"
    selected_path.write_text("synthetic", encoding="utf-8")
    resolved_path = selected_path.resolve(strict=False)
    original_stat = Path.stat

    def fail_selected_stat(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        if path == resolved_path:
            raise PermissionError("synthetic private metadata denial")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_selected_stat)

    with pytest.raises(PermissionError, match="synthetic private metadata"):
        proposal_desktop._inspect_git_worktree_ancestry(selected_path)


def test_selected_path_transient_metadata_errors_propagate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = tmp_path / "selected-private-file"
    selected_path.write_text("synthetic", encoding="utf-8")
    resolved_path = selected_path.resolve(strict=False)
    original_stat = Path.stat

    def fail_selected_stat(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        if path == resolved_path:
            raise OSError("synthetic transient metadata failure")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_selected_stat)

    with pytest.raises(OSError, match="synthetic transient metadata"):
        proposal_desktop._inspect_git_worktree_ancestry(selected_path)


def test_resolution_runtime_error_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = tmp_path / "selected-private-file"
    original_resolve = Path.resolve

    def fail_selected_resolution(path: Path, strict: bool = False) -> Path:
        if path == selected_path:
            raise RuntimeError("synthetic symlink loop")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_selected_resolution)

    with pytest.raises(RuntimeError, match="synthetic symlink loop"):
        proposal_desktop._inspect_git_worktree_ancestry(selected_path)


@pytest.mark.parametrize(
    "metadata_error",
    [
        PermissionError("synthetic marker permission failure"),
        OSError("synthetic marker transient failure"),
    ],
)
def test_dot_git_metadata_errors_propagate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_error: OSError,
) -> None:
    selected_path = tmp_path / "selected-private-file"
    selected_path.write_text("synthetic", encoding="utf-8")
    marker = selected_path.parent.resolve(strict=False) / ".git"
    original_lstat = Path.lstat

    def fail_marker_lstat(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        if path == marker:
            raise metadata_error
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fail_marker_lstat)

    with pytest.raises(type(metadata_error), match="synthetic marker"):
        proposal_desktop._inspect_git_worktree_ancestry(selected_path)


def test_any_existing_dot_git_entry_is_conservatively_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = tmp_path / "selected-private-file"
    selected_path.write_text("synthetic", encoding="utf-8")
    marker = selected_path.parent.resolve(strict=False) / ".git"
    original_lstat = Path.lstat

    def report_other_marker(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        if path == marker:
            return SimpleNamespace(st_mode=0)  # type: ignore[return-value]
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", report_other_marker)

    assert proposal_desktop.is_path_inside_git_worktree(selected_path) is True


def test_missing_dot_git_marker_continues_only_up_the_ancestor_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = tmp_path / "child" / "selected-private-file"
    selected_path.parent.mkdir()
    selected_path.write_text("synthetic", encoding="utf-8")
    first_marker = selected_path.parent.resolve(strict=False) / ".git"
    second_marker = selected_path.parent.parent.resolve(strict=False) / ".git"
    inspected_markers: list[Path] = []
    original_lstat = Path.lstat

    def inspect_markers(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        inspected_markers.append(path)
        if path == first_marker:
            raise FileNotFoundError
        if path == second_marker:
            return SimpleNamespace(st_mode=0)  # type: ignore[return-value]
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", inspect_markers)

    assert proposal_desktop.is_path_inside_git_worktree(selected_path) is True
    assert inspected_markers == [first_marker, second_marker]


@pytest.mark.parametrize(
    "metadata_error",
    [
        PermissionError("synthetic private permission failure"),
        OSError("synthetic private transient failure"),
        RuntimeError("synthetic private resolution failure"),
    ],
)
def test_initial_ancestry_failure_is_sanitized_and_blocks_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    metadata_error: Exception,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    private_database_path = Path(controller.state.database_path)
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry

    def fail_database_inspection(path: Path) -> tuple[Path, bool]:
        if path == private_database_path:
            raise metadata_error
        return original_inspect(path)

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        fail_database_inspection,
    )

    with pytest.raises(proposal_desktop.DesktopFormError) as error:
        controller.validate_draft()

    assert str(error.value) == (
        "Records Database ancestry could not be verified; revalidation is required."
    )
    assert str(private_database_path) not in str(error.value)
    assert harness.validation_calls == []
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []
    assert capsys.readouterr() == ("", "")


def test_metadata_failure_after_validation_revokes_authority_before_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    private_template_path = Path(controller.state.template_path)
    original_inspect = proposal_desktop._inspect_git_worktree_ancestry

    def fail_template_inspection(path: Path) -> tuple[Path, bool]:
        if path == private_template_path:
            raise PermissionError(str(private_template_path))
        return original_inspect(path)

    monkeypatch.setattr(
        proposal_desktop,
        "_inspect_git_worktree_ancestry",
        fail_template_inspection,
    )

    with pytest.raises(proposal_desktop.DesktopFormError) as error:
        controller.generate_draft()

    assert str(error.value) == (
        "DOCX Template ancestry could not be verified; revalidation is required."
    )
    assert str(private_template_path) not in str(error.value)
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_snapshot is None
    assert controller._validated_resolved_paths is None
    assert controller._validation_result is None
    assert controller.build_result is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()
    assert capsys.readouterr() == ("", "")


def test_worktree_probe_avoids_error_suppressing_metadata_shortcuts() -> None:
    source = inspect.getsource(proposal_desktop._inspect_git_worktree_ancestry)

    assert ".exists(" not in source
    assert ".is_dir(" not in source
    assert ".is_file(" not in source
    assert ".stat(" in source
    assert ".lstat(" in source


def test_dot_git_directory_appearing_after_validation_blocks_generation(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    output_root = Path(controller.state.output_root)
    (output_root / ".git").mkdir(parents=True)

    with pytest.raises(proposal_desktop.DesktopFormError, match="Output Root"):
        controller.generate_draft()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert not Path(controller.state.output_folder).exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()
    assert harness.opened_paths == []


def test_dot_git_file_appearing_after_validation_blocks_generation(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    output_root = Path(controller.state.output_root)
    output_root.mkdir(parents=True)
    (output_root / ".git").write_text("gitdir: ../synthetic-metadata", encoding="utf-8")

    with pytest.raises(proposal_desktop.DesktopFormError, match="Output Root"):
        controller.generate_draft()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert not Path(controller.state.output_folder).exists()
    assert not Path(controller.state.proposal_input_json_output_path).exists()
    assert not Path(controller.state.proposal_docx_output_path).exists()
    assert harness.opened_paths == []


def test_symlink_ancestry_retarget_after_validation_blocks_generation(
    tmp_path: Path,
) -> None:
    private_target = tmp_path / "private-target"
    worktree_target = tmp_path / "worktree-target"
    private_target.mkdir()
    (worktree_target / ".git").mkdir(parents=True)
    selected_root = tmp_path / "selected-root"
    try:
        os.symlink(private_target, selected_root, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlinks are unavailable: {exc}")

    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.propose_output_paths(selected_root)
    controller.validate_draft()
    selected_root.unlink()
    try:
        os.symlink(worktree_target, selected_root, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlink retargeting is unavailable: {exc}")

    with pytest.raises(proposal_desktop.DesktopFormError, match="Output Root"):
        controller.generate_draft()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert not Path(controller.state.output_folder).exists()
    assert harness.opened_paths == []


def test_private_symlink_retarget_after_validation_requires_revalidation(
    tmp_path: Path,
) -> None:
    first_private_target = tmp_path / "first-private-target"
    second_private_target = tmp_path / "second-private-target"
    first_private_target.mkdir()
    second_private_target.mkdir()
    selected_root = tmp_path / "selected-private-root"
    try:
        os.symlink(first_private_target, selected_root, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlinks are unavailable: {exc}")

    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.propose_output_paths(selected_root)
    controller.validate_draft()
    selected_root.unlink()
    try:
        os.symlink(second_private_target, selected_root, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlink retargeting is unavailable: {exc}")

    with pytest.raises(
        proposal_desktop.DesktopFormError,
        match="Output Root resolved location changed",
    ):
        controller.generate_draft()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller._validated_resolved_paths is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert not Path(controller.state.output_folder).exists()
    assert harness.opened_paths == []


@pytest.mark.parametrize(
    "amount_text",
    ["Infinity", "+Infinity", "-Infinity", "NaN", "-NaN", "sNaN"],
)
def test_non_finite_amounts_fail_before_validation_or_build(
    tmp_path: Path,
    amount_text: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_text_field("amount", amount_text)

    with pytest.raises(proposal_desktop.DesktopFormError, match="finite decimal"):
        controller.validate_draft()

    assert harness.validation_calls == []
    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()


@pytest.mark.parametrize("amount_text", ["125", "125.00", "0.01", "417.25"])
def test_finite_positive_amounts_reach_validation_unchanged(
    tmp_path: Path,
    amount_text: str,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.set_text_field("amount", amount_text)

    controller.validate_draft()

    assert len(harness.validation_calls) == 1
    assert harness.validation_calls[0].details.pricing.amount == Decimal(amount_text)
    assert harness.build_calls == []
    assert controller.generation_enabled is True


@pytest.mark.parametrize("amount_text", ["0", "-0.01"])
def test_finite_non_positive_amounts_remain_model_validation_failures(
    tmp_path: Path,
    amount_text: str,
) -> None:
    harness = _configured_controller(tmp_path)
    harness.controller.set_text_field("amount", amount_text)

    with pytest.raises(ValidationError):
        harness.controller.validate_draft()

    assert harness.validation_calls == []
    assert harness.build_calls == []
    assert harness.controller.generation_enabled is False


def test_malformed_amount_remains_an_explicit_decimal_parse_failure(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    harness.controller.set_text_field("amount", "not-a-decimal")

    with pytest.raises(proposal_desktop.DesktopFormError, match="valid ISO"):
        harness.controller.validate_draft()

    assert harness.validation_calls == []
    assert harness.build_calls == []
    assert harness.controller.generation_enabled is False


def test_sidecar_customer_reload_failure_revokes_validation_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _configure_real_validation_controller(tmp_path, monkeypatch)
    controller.validate_draft()
    database_path = Path(controller.state.database_path)
    database_before = _database_hash(database_path)
    sidecar = Path(f"{database_path}-wal")
    sidecar.write_bytes(b"synthetic-existing-sidecar")

    with pytest.raises(Exception):
        controller.load_customers()

    assert controller.customers == ()
    assert controller.jobs == ()
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert _database_hash(database_path) == database_before
    assert sidecar.read_bytes() == b"synthetic-existing-sidecar"
    assert not Path(controller.state.output_folder).exists()


def test_database_path_change_safely_clears_both_comboboxes_and_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(0)
    app_harness.job_combo.current(0)
    app_harness.customer_variable.set("Synthetic Customer")
    app_harness.job_variable.set("Synthetic Tank Project")
    app_harness.app._variables["database_path"].set(
        str(tmp_path / "replacement-records.sqlite")
    )

    app_harness.app._on_text_field_changed("database_path")

    assert app_harness.customer_combo.values == ()
    assert app_harness.customer_combo.current() == -1
    assert app_harness.customer_variable.get() == ""
    assert app_harness.job_combo.values == ()
    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert controller.customers == ()
    assert controller.jobs == ()
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()


def test_successful_customer_load_safely_leaves_both_selections_blank(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(0)
    app_harness.job_combo.current(0)
    app_harness.customer_variable.set("Synthetic Customer")
    app_harness.job_variable.set("Synthetic Tank Project")

    app_harness.app._load_customers()

    assert app_harness.customer_combo.values == controller.customer_display_labels
    assert app_harness.customer_combo.current() == -1
    assert app_harness.customer_variable.get() == ""
    assert app_harness.job_combo.values == ()
    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()


def test_customer_selection_safely_clears_previous_job_selection(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(0)
    app_harness.customer_variable.set("Synthetic Customer")
    app_harness.job_combo.current(0)
    app_harness.job_variable.set("Synthetic Tank Project")

    app_harness.app._on_customer_selected()

    assert controller.state.selected_customer_id == "customer-synthetic-001"
    assert controller.state.selected_job_id == ""
    assert app_harness.job_combo.values == controller.job_display_labels
    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert not Path(controller.state.output_folder).exists()


def test_gui_validation_failure_clears_summary_and_disables_all_actions(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    controller.generate_draft()
    app_harness = _headless_app(controller)

    def fail_validation(
        _request: ProposalDraftBuildRequest,
    ) -> ProposalDraftValidationResult:
        raise proposal_desktop.DesktopFormError("Synthetic validation failure")

    controller._validation_function = fail_validation

    app_harness.app._validate()

    assert app_harness.summary_text.content == ""
    assert app_harness.status_variable.value.startswith("Validation failed")
    assert app_harness.generate_button.state == "disabled"
    assert all(button.state == "disabled" for button in app_harness.open_buttons)
    assert len(app_harness.messagebox.errors) == 1
    assert controller.validated_request is None
    assert harness.opened_paths == []
    assert len(harness.build_calls) == 1


def test_gui_customer_reload_failure_clears_customer_and_job_combos(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(0)
    app_harness.job_combo.current(0)
    app_harness.customer_variable.set("Synthetic Customer")
    app_harness.job_variable.set("Synthetic Tank Project")

    def fail_customer_repository(*_args: object, **_kwargs: object) -> Any:
        raise OSError("Synthetic immutable customer read failure")

    controller._customer_repository_factory = fail_customer_repository

    app_harness.app._load_customers()

    assert app_harness.customer_combo.values == ()
    assert app_harness.customer_combo.current() == -1
    assert app_harness.customer_variable.get() == ""
    assert app_harness.job_combo.values == ()
    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert app_harness.summary_text.content == ""
    assert app_harness.generate_button.state == "disabled"
    assert len(app_harness.messagebox.errors) == 1
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert all(
        variable.get() == ""
        for variable in app_harness.app._customer_edit_variables.values()
    )
    assert app_harness.app._customer_edit_notes_text.content == ""


def test_gui_customer_selection_failure_clears_customer_and_job_combos(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.customer_combo.current(1)
    app_harness.job_combo.current(0)
    app_harness.customer_variable.set("Synthetic Customer")
    app_harness.job_variable.set("Synthetic Tank Project")

    class FailingJobRepository:
        def list_jobs_for_customer(self, _customer_id: str) -> list[JobRecord]:
            raise OSError("Synthetic immutable job read failure")

    controller._job_repository_factory = (
        lambda *_args, **_kwargs: FailingJobRepository()
    )

    app_harness.app._on_customer_selected()

    assert app_harness.customer_combo.values == ()
    assert app_harness.customer_combo.current() == -1
    assert app_harness.customer_variable.get() == ""
    assert app_harness.job_combo.values == ()
    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert controller.state.selected_customer_id == ""
    assert controller.state.selected_job_id == ""
    assert app_harness.generate_button.state == "disabled"
    assert len(app_harness.messagebox.errors) == 1
    assert harness.build_calls == []
    assert harness.opened_paths == []
    assert all(
        variable.get() == ""
        for variable in app_harness.app._customer_edit_variables.values()
    )
    assert app_harness.app._customer_edit_notes_text.content == ""


def test_gui_job_selection_failure_clears_job_combo_and_generation_authority(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    app_harness.job_combo.current(99)
    app_harness.job_variable.set("Stale Synthetic Job")

    app_harness.app._on_job_selected()

    assert app_harness.job_combo.current() == -1
    assert app_harness.job_variable.get() == ""
    assert controller.state.selected_job_id == ""
    assert controller.validated_request is None
    assert app_harness.generate_button.state == "disabled"
    assert all(button.state == "disabled" for button in app_harness.open_buttons)
    assert len(app_harness.messagebox.errors) == 1
    assert harness.build_calls == []
    assert harness.opened_paths == []


def test_gui_successful_generation_reports_selected_docx_path(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    selected = tmp_path / "selected-output" / "controlled-proposal.docx"
    controller.select_docx_output_path(selected)
    controller.validate_draft()
    validated_request = controller.validated_request
    app_harness = _headless_app(controller)

    app_harness.app._generate()

    assert harness.build_calls == [validated_request]
    assert harness.build_calls[0] is validated_request
    assert str(selected) in app_harness.status_variable.value
    assert app_harness.status_variable.value.startswith("Generated local artifacts")
    assert all(button.state == "normal" for button in app_harness.open_buttons)
    assert harness.opened_paths == []
    assert app_harness.messagebox.errors == []


def test_gui_failed_rebuild_clears_prior_paths_and_disables_open_actions(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    result = controller.generate_draft()
    app_harness = _headless_app(controller)
    app_harness.status_variable.set(str(result.proposal_docx_path))

    def fail_build(_request: ProposalDraftBuildRequest) -> ProposalDraftBuildResult:
        raise proposal_desktop.DesktopFormError("Synthetic build failure")

    controller._build_function = fail_build

    app_harness.app._generate()

    assert controller.build_result is None
    assert controller.generation_enabled is True
    assert app_harness.status_variable.value.startswith("Generation failed")
    assert str(result.proposal_docx_path) not in app_harness.status_variable.value
    assert all(button.state == "disabled" for button in app_harness.open_buttons)
    assert len(app_harness.messagebox.errors) == 1
    assert harness.opened_paths == []


def test_gui_worktree_change_failure_requires_revalidation_and_clears_summary(
    tmp_path: Path,
) -> None:
    harness = _configured_controller(tmp_path)
    controller = harness.controller
    controller.validate_draft()
    app_harness = _headless_app(controller)
    previous_path_text = str(Path(controller.state.proposal_docx_output_path))
    app_harness.status_variable.set(previous_path_text)
    output_root = Path(controller.state.output_root)
    (output_root / ".git").mkdir(parents=True)

    app_harness.app._generate()

    assert harness.build_calls == []
    assert controller.validated_request is None
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert app_harness.summary_text.content == ""
    assert app_harness.status_variable.value == (
        "Generation blocked; revalidation is required."
    )
    assert previous_path_text not in app_harness.status_variable.value
    assert app_harness.generate_button.state == "disabled"
    assert all(button.state == "disabled" for button in app_harness.open_buttons)
    assert len(app_harness.messagebox.errors) == 1
    assert harness.opened_paths == []


def test_controller_construction_and_state_editing_have_no_side_effects(
    tmp_path: Path,
) -> None:
    opened: list[Path] = []
    controller = proposal_desktop.ProposalDesktopController(
        validation_function=lambda _request: pytest.fail("validation called"),
        build_function=lambda _request: pytest.fail("build called"),
        customer_repository_factory=lambda *_args, **_kwargs: pytest.fail(
            "customer repository opened"
        ),
        job_repository_factory=lambda *_args, **_kwargs: pytest.fail(
            "job repository opened"
        ),
        path_opener=opened.append,
        clock=lambda: NOW,
    )
    controller.set_text_field("database_path", str(tmp_path / "missing.sqlite"))
    controller.set_text_field("template_path", str(tmp_path / "missing.docx"))
    controller.propose_output_paths(tmp_path / "output")
    controller.set_text_field("item_description", "Explicit synthetic wording")
    controller.set_scope_description(0, "Explicit synthetic scope")

    assert list(tmp_path.iterdir()) == []
    assert opened == []


def test_source_adds_no_logging_network_shell_or_private_service_reimplementation() -> None:
    source = inspect.getsource(proposal_desktop)

    assert "import logging" not in source
    assert "import requests" not in source
    assert "import urllib" not in source
    assert "shell=True" not in source
    assert "DocxProposalRenderer" not in source
    assert "_select_existing_proposal_records" not in source
    assert "_proposal_summary_lines" not in source
    assert "save_customer(" not in source
    assert "save_job(" not in source
    assert "initialize_records_database" not in source


def test_main_loads_toolkit_lazily_creates_one_root_and_runs_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class Root:
        def mainloop(self) -> None:
            calls.append("mainloop")

    root = Root()
    tk = SimpleNamespace(Tk=lambda: calls.append("Tk") or root)
    toolkit = (tk, object(), object(), object())

    monkeypatch.setattr(proposal_desktop, "_load_tkinter", lambda: toolkit)
    monkeypatch.setattr(
        proposal_desktop,
        "ProposalDesktopApp",
        lambda received_root, *, toolkit: calls.append((received_root, toolkit)),
    )

    assert proposal_desktop.main() == 0
    assert calls == ["Tk", (root, toolkit), "mainloop"]


def test_module_entrypoint_and_authorized_public_service_calls_are_present() -> None:
    source = inspect.getsource(proposal_desktop)

    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
    assert "validate_proposal_draft(request)" not in source
    assert "self._validation_function(request)" in source
    assert "self._build_function(request)" in source
    assert "ProposalDraftBuildRequest(" in source
    assert "RecordProposalDetails(" in source
    assert "ScopeItem(number=index, description=description)" in source
    assert "PricingLine(" in source
    assert "CompanyConfig(" in source


def test_default_local_opener_uses_no_browser_and_no_shell_true() -> None:
    source = inspect.getsource(proposal_desktop._open_local_path)

    assert "webbrowser" not in source
    assert "shell=True" not in source
    assert "[command, str(path)]" in source
    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
