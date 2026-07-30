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
from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.proposal_build import (
    ProposalDraftBuildRequest,
    ProposalDraftBuildResult,
    ProposalDraftValidationResult,
)
from phoenix_office.records import SQLiteCustomerRepository, SQLiteJobRepository

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
    job_factory_calls: list[tuple[Path, bool, bool]]
    job_list_calls: list[str]
    validation_calls: list[ProposalDraftBuildRequest]
    build_calls: list[ProposalDraftBuildRequest]
    opened_paths: list[Path]


class FakeVariable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeCombo:
    def __init__(self, *, values: tuple[str, ...] = (), current: int = -1) -> None:
        self.values = values
        self.current_index = current

    def configure(self, **kwargs: object) -> None:
        if "values" in kwargs:
            self.values = tuple(kwargs["values"])  # type: ignore[arg-type]

    def current(self, index: int | None = None) -> int:
        if index is not None:
            self.current_index = index
        return self.current_index


class FakeText:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.state = "disabled"

    def configure(self, **kwargs: object) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])

    def delete(self, _start: str, _end: str) -> None:
        self.content = ""

    def insert(self, _start: str, value: str) -> None:
        self.content = value


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
    app.controller = controller
    app._root = object()
    app._messagebox = messagebox
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
    )


def _configured_controller(
    tmp_path: Path,
    *,
    customers: tuple[CustomerRecord, ...] | None = None,
    jobs: tuple[JobRecord, ...] | None = None,
) -> ControllerHarness:
    customer_records = customers or (
        _customer(),
        _customer("customer-synthetic-002", "Synthetic Customer"),
    )
    job_records = jobs or (
        _job(),
        _job("job-synthetic-002", job_name="Synthetic Inspection"),
        _job(
            "job-synthetic-003",
            customer_id="customer-synthetic-002",
            job_name="Synthetic Secondary Project",
        ),
    )
    customer_factory_calls: list[tuple[Path, bool, bool]] = []
    job_factory_calls: list[tuple[Path, bool, bool]] = []
    job_list_calls: list[str] = []
    validation_calls: list[ProposalDraftBuildRequest] = []
    build_calls: list[ProposalDraftBuildRequest] = []
    opened_paths: list[Path] = []

    class CustomerRepository:
        def list_customers(self) -> list[CustomerRecord]:
            return list(customer_records)

    class JobRepository:
        def list_jobs_for_customer(self, customer_id: str) -> list[JobRecord]:
            job_list_calls.append(customer_id)
            return [job for job in job_records if job.customer_id == customer_id]

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
        job_repository_factory=job_factory,
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
        job_factory_calls=job_factory_calls,
        job_list_calls=job_list_calls,
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
        harness.controller.create_request()


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
    assert controller.validation_summary_lines == ()
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []


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
    assert controller.validation_summary_lines == ()
    assert controller.generation_enabled is False
    assert controller.open_actions_enabled is False
    assert len(harness.build_calls) == 1
    assert harness.opened_paths == []


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

    def detect_selected_worktree(path: Path) -> bool:
        resolved = path.resolve(strict=False)
        checked_paths.append(resolved)
        return resolved == blocked_path

    monkeypatch.setattr(
        proposal_desktop,
        "is_path_inside_git_worktree",
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

    def record_private_path(path: Path) -> bool:
        checked_paths.append(path)
        return False

    monkeypatch.setattr(
        proposal_desktop,
        "is_path_inside_git_worktree",
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
