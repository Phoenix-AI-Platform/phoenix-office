"""Read-only application service for record-backed proposal builds."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from docx import Document
from pydantic import ValidationError

from phoenix_office.models.proposal import ProposalInput
from phoenix_office.proposal_placeholder_validation import (
    proposal_input_placeholder_paths,
)
from phoenix_office.records import (
    RecordProposalDetails,
    RecordStore,
    SQLiteCustomerRepository,
    SQLiteJobRepository,
    create_proposal_input_from_record_details,
)
from phoenix_office.renderers import DocxProposalRenderer


@dataclass(frozen=True, slots=True)
class ProposalDraftBuildRequest:
    """Explicit inputs for one deterministic record-backed proposal build."""

    customer_id: str
    job_id: str
    details: RecordProposalDetails
    database_path: Path
    template_path: Path
    proposal_input_json_output_path: Path
    proposal_docx_output_path: Path


@dataclass(frozen=True, slots=True)
class ProposalDraftBuildResult:
    """Published artifacts and summary data from a successful proposal build."""

    proposal_input: ProposalInput
    proposal_input_json_path: Path
    proposal_docx_path: Path
    summary_lines: tuple[str, ...]


class _ProposalDraftBuildFailure(Exception):
    """Sanitized service failure intended for an operator-facing adapter."""

    def __init__(self, *stderr_lines: str) -> None:
        super().__init__("\n".join(stderr_lines))
        self.stderr_lines = tuple(stderr_lines)


def build_proposal_draft(request: ProposalDraftBuildRequest) -> ProposalDraftBuildResult:
    """Build and publish one proposal from existing records and explicit details.

    The service never initializes or mutates the records database. Both output
    artifacts are staged as temporary siblings and exclusively published as one
    logical operation; any partial publication is rolled back on failure.
    """

    output_json_path = request.proposal_input_json_output_path
    output_docx_path = request.proposal_docx_output_path
    database_path = request.database_path
    template_path = request.template_path

    _validate_output_paths(output_json_path, output_docx_path)
    _validate_database_path(database_path)
    _validate_template_path(template_path)

    try:
        store = RecordStore(
            customers=SQLiteCustomerRepository(
                database_path,
                initialize=False,
                read_only=True,
            ),
            jobs=SQLiteJobRepository(
                database_path,
                initialize=False,
                read_only=True,
            ),
        )
        customer = store.customers.get_customer(request.customer_id)
    except Exception as exc:  # noqa: BLE001 - sanitize database errors.
        raise _ProposalDraftBuildFailure(
            f"Error: failed to read records database: {database_path}"
        ) from exc
    if customer is None:
        raise _ProposalDraftBuildFailure(
            f"Customer not found: {request.customer_id}"
        )

    try:
        job = store.jobs.get_job(request.job_id)
    except Exception as exc:  # noqa: BLE001 - sanitize database errors.
        raise _ProposalDraftBuildFailure(
            f"Error: failed to read records database: {database_path}"
        ) from exc
    if job is None:
        raise _ProposalDraftBuildFailure(f"Job not found: {request.job_id}")

    try:
        proposal = create_proposal_input_from_record_details(
            customer=customer,
            job=job,
            details=request.details,
        )
    except (ValueError, ValidationError) as exc:
        raise _ProposalDraftBuildFailure(
            "Error: failed to compose proposal input for "
            f"customer {request.customer_id} and job {request.job_id}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - sanitize composition errors.
        raise _ProposalDraftBuildFailure(
            "Error: unexpected proposal composition failure for "
            f"customer {request.customer_id} and job {request.job_id}"
        ) from exc

    placeholder_paths = proposal_input_placeholder_paths(proposal)
    if placeholder_paths:
        raise _ProposalDraftBuildFailure(
            "Error: unresolved placeholder text in composed proposal; "
            "refusing proposal build.",
            "Placeholder fields: " + ", ".join(placeholder_paths),
        )

    staged_paths: list[Path] = []
    created_final_paths: list[Path] = []
    completed = False
    try:
        try:
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            output_docx_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - sanitize output-directory errors.
            raise _ProposalDraftBuildFailure(
                "Error: failed to prepare proposal output directories"
            ) from exc

        try:
            staged_json_path = _create_temporary_sibling(output_json_path)
            staged_paths.append(staged_json_path)
            _write_proposal_input_json(proposal, staged_json_path)
        except Exception as exc:  # noqa: BLE001 - sanitize serialization errors.
            raise _ProposalDraftBuildFailure(
                f"Error: failed to stage proposal input JSON: {output_json_path}"
            ) from exc

        try:
            staged_docx_path = _create_temporary_sibling(output_docx_path)
            staged_paths.append(staged_docx_path)
            DocxProposalRenderer().render(proposal, template_path, staged_docx_path)
            if not staged_docx_path.exists() or staged_docx_path.stat().st_size == 0:
                raise ValueError("staged DOCX is missing or empty")
        except Exception as exc:  # noqa: BLE001 - sanitize rendering errors.
            raise _ProposalDraftBuildFailure(
                f"Error: failed to render proposal DOCX: {output_docx_path}"
            ) from exc

        if not staged_json_path.exists() or not staged_docx_path.exists():
            raise _ProposalDraftBuildFailure(
                "Error: proposal output staging did not produce both artifacts"
            )

        try:
            _publish_staged_artifact(
                staged_json_path,
                output_json_path,
                created_final_paths,
            )
            _publish_staged_artifact(
                staged_docx_path,
                output_docx_path,
                created_final_paths,
            )
        except Exception as exc:  # noqa: BLE001 - exclusive publication boundary.
            raise _ProposalDraftBuildFailure(
                "Error: failed to publish final proposal outputs"
            ) from exc

        if (
            not output_json_path.exists()
            or not output_docx_path.exists()
            or output_docx_path.stat().st_size == 0
        ):
            raise _ProposalDraftBuildFailure(
                "Error: final proposal output verification failed"
            )

        completed = True
    finally:
        for staged_path in staged_paths:
            staged_path.unlink(missing_ok=True)
        if not completed:
            for final_path in reversed(created_final_paths):
                final_path.unlink(missing_ok=True)

    return ProposalDraftBuildResult(
        proposal_input=proposal,
        proposal_input_json_path=output_json_path,
        proposal_docx_path=output_docx_path,
        summary_lines=_proposal_summary_lines(proposal),
    )


def _validate_output_paths(output_json_path: Path, output_docx_path: Path) -> None:
    if output_json_path.resolve() == output_docx_path.resolve():
        raise _ProposalDraftBuildFailure(
            "Error: proposal output paths must be different"
        )

    existing_output_errors: list[str] = []
    if output_json_path.exists():
        existing_output_errors.append(
            f"Error: proposal input JSON output already exists: {output_json_path}"
        )
    if output_docx_path.exists():
        existing_output_errors.append(
            f"Error: proposal DOCX output already exists: {output_docx_path}"
        )
    if existing_output_errors:
        raise _ProposalDraftBuildFailure(*existing_output_errors)


def _validate_database_path(database_path: Path) -> None:
    if not database_path.exists():
        raise _ProposalDraftBuildFailure(
            f"Error: records database does not exist: {database_path}"
        )
    if not database_path.is_file():
        raise _ProposalDraftBuildFailure(
            f"Error: records database path is not a file: {database_path}"
        )


def _validate_template_path(template_path: Path) -> None:
    if not template_path.exists():
        raise _ProposalDraftBuildFailure(
            f"Error: DOCX template file does not exist: {template_path}"
        )
    if not template_path.is_file():
        raise _ProposalDraftBuildFailure(
            f"Error: DOCX template path is not a file: {template_path}"
        )
    try:
        Document(str(template_path))
    except Exception as exc:  # noqa: BLE001 - sanitize untrusted template errors.
        raise _ProposalDraftBuildFailure(
            f"Error: DOCX template is not usable: {template_path}"
        ) from exc


def _proposal_summary_lines(proposal: ProposalInput) -> tuple[str, ...]:
    lines = [
        f"Customer: {proposal.customer_name}",
        f"Site Address: {proposal.street_address}, {proposal.city_state_zip}",
        f"Item Description: {proposal.item_description}",
        f"Scope Items: {len(proposal.scope_items)}",
        "Pricing Lines: 1",
        f"Total: {_format_proposal_total(proposal)}",
        f"Notes: {'present' if proposal.notes else 'none'}",
    ]
    if proposal.company_config.company_name:
        lines.append(f"Company: {proposal.company_config.company_name}")
    return tuple(lines)


def _format_proposal_total(proposal: ProposalInput) -> str:
    amount = f"${proposal.pricing.amount:,.2f}"
    if proposal.pricing.is_starting_at:
        return f"{proposal.company_config.starting_at_label} {amount}"
    return amount


def _write_proposal_input_json(proposal: ProposalInput, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = proposal.model_dump(mode="json")
    output_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _create_temporary_sibling(final_path: Path) -> Path:
    with NamedTemporaryFile(
        mode="wb",
        prefix=f".{final_path.name}.",
        suffix=".tmp",
        dir=final_path.parent,
        delete=False,
    ) as temporary_file:
        return Path(temporary_file.name)


def _publish_staged_artifact(
    staged_path: Path,
    final_path: Path,
    created_final_paths: list[Path],
) -> None:
    with staged_path.open("rb") as source:
        with final_path.open("xb") as destination:
            created_final_paths.append(final_path)
            shutil.copyfileobj(source, destination)
