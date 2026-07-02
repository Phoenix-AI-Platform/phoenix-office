"""Command-line interface for Phoenix Office."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from phoenix_office.dev_status import (
    DEFAULT_PROJECT_STATE_PATH,
    format_development_status,
    format_development_status_json,
    read_development_status,
)
from phoenix_office.models.proposal import ProposalInput
from phoenix_office.orchestration import WorkflowPlan, WorkflowPlanReview
from phoenix_office.plugins.registry import get_registered_plugin_capabilities
from phoenix_office.proposal_intake import collect_proposal_input
from phoenix_office.proposal_intake_normalization import (
    A1ProposalPricingLine,
    a1_proposal_intake_draft_from_customer_record,
    a1_proposal_intake_from_dict,
)
from phoenix_office.proposal_placeholder_validation import (
    proposal_input_placeholder_paths,
)
from phoenix_office.records import (
    create_proposal_input_from_record_details,
    create_sqlite_record_store,
    customer_record_from_json_file,
    customer_record_to_json,
    customer_records_to_json,
    export_customer_records_file,
    export_job_records_file,
    import_customer_record_file,
    import_customer_records_file,
    import_job_record_file,
    import_job_records_file,
    job_record_to_json,
    job_records_to_json,
    record_proposal_details_from_file,
)
from phoenix_office.renderers import DocxProposalRenderer

DEV_STATUS_PROJECT_STATE_PATH = DEFAULT_PROJECT_STATE_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phoenix-office")
    subparsers = parser.add_subparsers(dest="command")

    dev_parser = subparsers.add_parser(
        "dev",
        help="Inspect Phoenix Office development state",
    )
    dev_subparsers = dev_parser.add_subparsers(dest="dev_command")
    dev_status_parser = dev_subparsers.add_parser(
        "status",
        help="Show read-only development status",
    )
    dev_status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output development status as JSON",
    )
    dev_status_parser.set_defaults(func=dev_status)

    proposal_parser = subparsers.add_parser("proposal", help="Proposal commands")
    proposal_subparsers = proposal_parser.add_subparsers(dest="proposal_command")

    generate_parser = proposal_subparsers.add_parser(
        "generate",
        help="Generate a proposal DOCX from JSON input",
    )
    generate_parser.add_argument("input_json", type=Path, help="Path to proposal JSON input")
    generate_parser.add_argument("output_docx", type=Path, help="Path for the generated DOCX")
    generate_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the DOCX template",
    )
    generate_parser.add_argument(
        "--allow-placeholder-proposal-input",
        action="store_true",
        help=(
            "Allow DOCX generation when proposal input contains unresolved "
            "placeholder text"
        ),
    )
    generate_parser.set_defaults(func=generate_proposal)
    validate_proposal_parser = proposal_subparsers.add_parser(
        "validate",
        help="Validate a proposal JSON input file",
    )
    validate_proposal_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to proposal JSON input",
    )
    validate_proposal_parser.set_defaults(func=validate_proposal)

    inspect_proposal_parser = proposal_subparsers.add_parser(
        "inspect",
        help="Inspect a proposal JSON input file",
    )
    inspect_proposal_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to proposal JSON input",
    )
    inspect_proposal_parser.add_argument(
        "--json",
        action="store_true",
        help="Output normalized proposal input as JSON",
    )
    inspect_proposal_parser.set_defaults(func=inspect_proposal)
    draft_json_parser = proposal_subparsers.add_parser(
        "draft-json",
        help="Create an editable starter A-1 proposal intake JSON file",
    )
    draft_json_parser.add_argument(
        "output_json",
        type=Path,
        help="Path for the starter A-1 proposal intake JSON",
    )
    draft_json_parser.add_argument(
        "--customer-name",
        help="Customer name to place in a customer-specific starter draft",
    )
    draft_json_parser.add_argument(
        "--street-address",
        help="Job street address to place in a customer-specific starter draft",
    )
    draft_json_parser.add_argument(
        "--city-state-zip",
        help="Job city, state, and ZIP to place in a customer-specific starter draft",
    )
    draft_json_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing starter proposal draft JSON file",
    )
    draft_json_parser.set_defaults(func=create_proposal_draft_json)

    customer_draft_json_parser = proposal_subparsers.add_parser(
        "customer-draft-json",
        help="Create an A-1 proposal intake JSON file from a customer record",
    )
    customer_draft_json_parser.add_argument(
        "customer_json",
        type=Path,
        help="Path to CustomerRecord JSON input",
    )
    customer_draft_json_parser.add_argument(
        "output_json",
        type=Path,
        help="Path for the customer-backed A-1 proposal intake JSON",
    )
    customer_draft_json_parser.add_argument(
        "--proposal-date",
        required=True,
        help="Explicit proposal date in YYYY-MM-DD format",
    )
    customer_draft_json_parser.add_argument(
        "--item-description",
        required=True,
        help="Explicit proposal item description",
    )
    customer_draft_json_parser.add_argument(
        "--scope-note",
        action="append",
        required=True,
        help="Explicit proposal scope note; repeat for multiple scope items",
    )
    customer_draft_json_parser.add_argument(
        "--pricing-description",
        required=True,
        help="Explicit pricing line description",
    )
    customer_draft_json_parser.add_argument(
        "--pricing-amount",
        required=True,
        help="Explicit pricing amount in USD",
    )
    customer_draft_json_parser.add_argument(
        "--pricing-note",
        help="Optional explicit pricing note",
    )
    customer_draft_json_parser.add_argument(
        "--starting-at",
        action="store_true",
        help="Mark the explicit price as a starting-at amount",
    )
    customer_draft_json_parser.add_argument(
        "--special-note",
        action="append",
        required=True,
        help="Explicit proposal special note; repeat for multiple notes",
    )
    customer_draft_json_parser.add_argument(
        "--company-name",
        default="A-1 Tank Removal LLC",
        help="Explicit company name for the intake draft",
    )
    customer_draft_json_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing customer-backed proposal draft JSON file",
    )
    customer_draft_json_parser.set_defaults(func=create_customer_proposal_draft_json)

    intake_normalize_parser = proposal_subparsers.add_parser(
        "intake-normalize",
        help="Normalize an explicit A-1 intake JSON file into ProposalInput JSON",
    )
    intake_normalize_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to A-1 proposal intake JSON input",
    )
    intake_normalize_parser.add_argument(
        "output_json",
        type=Path,
        help="Path for normalized ProposalInput JSON output",
    )
    intake_normalize_parser.set_defaults(func=normalize_proposal_intake)
    intake_validate_parser = proposal_subparsers.add_parser(
        "intake-validate",
        help="Validate an explicit A-1 intake JSON file",
    )
    intake_validate_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to A-1 proposal intake JSON input",
    )
    intake_validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the A-1 intake validation result as JSON",
    )
    intake_validate_parser.set_defaults(func=validate_proposal_intake)
    intake_inspect_parser = proposal_subparsers.add_parser(
        "intake-inspect",
        help="Inspect an explicit A-1 intake JSON file",
    )
    intake_inspect_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to A-1 proposal intake JSON input",
    )
    intake_inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the validated A-1 intake summary as JSON",
    )
    intake_inspect_parser.set_defaults(func=inspect_proposal_intake)
    generate_from_intake_parser = proposal_subparsers.add_parser(
        "generate-from-intake",
        help="Generate a proposal DOCX from explicit A-1 intake JSON",
    )
    generate_from_intake_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to A-1 proposal intake JSON input",
    )
    generate_from_intake_parser.add_argument(
        "output_docx",
        type=Path,
        help="Path for the generated DOCX",
    )
    generate_from_intake_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the DOCX template",
    )
    generate_from_intake_parser.add_argument(
        "--allow-placeholder-intake",
        action="store_true",
        help="Allow DOCX generation when intake contains unresolved placeholder text",
    )
    generate_from_intake_parser.set_defaults(func=generate_proposal_from_intake)

    intake_parser = proposal_subparsers.add_parser(
        "intake",
        help="Collect proposal details interactively and generate a DOCX",
    )
    intake_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the DOCX template",
    )
    intake_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the generated DOCX",
    )
    intake_parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the collected proposal JSON",
    )
    intake_parser.set_defaults(func=intake_proposal)

    capabilities_parser = subparsers.add_parser(
        "capabilities",
        help="Inspect registered Phoenix plugin capabilities",
    )
    capabilities_subparsers = capabilities_parser.add_subparsers(
        dest="capabilities_command"
    )
    list_parser = capabilities_subparsers.add_parser(
        "list",
        help="List registered Phoenix plugin capabilities",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output registered capabilities as JSON",
    )
    list_parser.set_defaults(func=list_capabilities)

    tasks_parser = subparsers.add_parser(
        "tasks",
        help="Inspect serialized Phoenix task envelopes",
    )
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")
    show_parser = tasks_subparsers.add_parser(
        "show",
        help="Show a serialized Phoenix TaskEnvelope JSON file",
    )
    show_parser.add_argument(
        "task_json",
        type=Path,
        help="Path to serialized TaskEnvelope JSON",
    )
    show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the loaded TaskEnvelope JSON with sorted keys",
    )
    show_parser.set_defaults(func=show_task)

    validate_parser = tasks_subparsers.add_parser(
        "validate",
        help="Validate a serialized Phoenix TaskEnvelope JSON file",
    )
    validate_parser.add_argument(
        "task_json",
        type=Path,
        help="Path to serialized TaskEnvelope JSON",
    )
    validate_parser.set_defaults(func=validate_task)

    orchestration_parser = subparsers.add_parser(
        "orchestration",
        help="Inspect orchestration contracts",
    )
    orchestration_subparsers = orchestration_parser.add_subparsers(
        dest="orchestration_command"
    )
    orchestration_plan_parser = orchestration_subparsers.add_parser(
        "plan",
        help="Inspect workflow plan contracts",
    )
    orchestration_plan_subparsers = orchestration_plan_parser.add_subparsers(
        dest="orchestration_plan_command"
    )
    orchestration_plan_inspect_parser = orchestration_plan_subparsers.add_parser(
        "inspect",
        help="Inspect a WorkflowPlan JSON file without executing it",
    )
    orchestration_plan_inspect_parser.add_argument(
        "plan_json",
        type=Path,
        help="Path to serialized WorkflowPlan JSON",
    )
    orchestration_plan_inspect_parser.set_defaults(func=inspect_workflow_plan)

    orchestration_review_parser = orchestration_subparsers.add_parser(
        "review",
        help="Inspect workflow plan review contracts",
    )
    orchestration_review_subparsers = orchestration_review_parser.add_subparsers(
        dest="orchestration_review_command"
    )
    orchestration_review_inspect_parser = orchestration_review_subparsers.add_parser(
        "inspect",
        help="Inspect a WorkflowPlanReview JSON file without mutating it",
    )
    orchestration_review_inspect_parser.add_argument(
        "review_json",
        type=Path,
        help="Path to serialized WorkflowPlanReview JSON",
    )
    orchestration_review_inspect_parser.set_defaults(func=inspect_workflow_plan_review)

    records_parser = subparsers.add_parser(
        "records",
        help="Record commands",
    )
    records_subparsers = records_parser.add_subparsers(dest="records_command")
    records_import_parser = records_subparsers.add_parser(
        "import",
        help="Import record JSON files into a SQLite database",
    )
    records_import_subparsers = records_import_parser.add_subparsers(
        dest="records_import_kind"
    )

    customer_import_parser = records_import_subparsers.add_parser(
        "customer",
        help="Import one CustomerRecord JSON file",
    )
    customer_import_parser.add_argument(
        "json_path",
        type=Path,
        help="Path to CustomerRecord JSON",
    )
    customer_import_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    customer_import_parser.set_defaults(func=import_records, records_import_kind="customer")

    job_import_parser = records_import_subparsers.add_parser(
        "job",
        help="Import one JobRecord JSON file",
    )
    job_import_parser.add_argument(
        "json_path",
        type=Path,
        help="Path to JobRecord JSON",
    )
    job_import_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    job_import_parser.set_defaults(func=import_records, records_import_kind="job")

    customers_import_parser = records_import_subparsers.add_parser(
        "customers",
        help="Import a CustomerRecord JSON array file",
    )
    customers_import_parser.add_argument(
        "json_path",
        type=Path,
        help="Path to CustomerRecord JSON array",
    )
    customers_import_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    customers_import_parser.set_defaults(func=import_records, records_import_kind="customers")

    jobs_import_parser = records_import_subparsers.add_parser(
        "jobs",
        help="Import a JobRecord JSON array file",
    )
    jobs_import_parser.add_argument(
        "json_path",
        type=Path,
        help="Path to JobRecord JSON array",
    )
    jobs_import_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    jobs_import_parser.set_defaults(func=import_records, records_import_kind="jobs")

    records_list_parser = records_subparsers.add_parser(
        "list",
        help="List records from a SQLite database",
    )
    records_list_subparsers = records_list_parser.add_subparsers(dest="records_list_kind")

    customers_list_parser = records_list_subparsers.add_parser(
        "customers",
        help="List CustomerRecord rows",
    )
    customers_list_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    customers_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output customers as JSON",
    )
    customers_list_parser.set_defaults(func=list_records, records_list_kind="customers")

    jobs_list_parser = records_list_subparsers.add_parser(
        "jobs",
        help="List JobRecord rows",
    )
    jobs_list_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    jobs_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output jobs as JSON",
    )
    jobs_list_parser.set_defaults(func=list_records, records_list_kind="jobs")

    records_show_parser = records_subparsers.add_parser(
        "show",
        help="Show one record from a SQLite database",
    )
    records_show_subparsers = records_show_parser.add_subparsers(dest="records_show_kind")

    customer_show_parser = records_show_subparsers.add_parser(
        "customer",
        help="Show one CustomerRecord row",
    )
    customer_show_parser.add_argument(
        "customer_id",
        help="Customer ID to show",
    )
    customer_show_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    customer_show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output customer as JSON",
    )
    customer_show_parser.set_defaults(func=show_record, records_show_kind="customer")

    job_show_parser = records_show_subparsers.add_parser(
        "job",
        help="Show one JobRecord row",
    )
    job_show_parser.add_argument(
        "job_id",
        help="Job ID to show",
    )
    job_show_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    job_show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output job as JSON",
    )
    job_show_parser.set_defaults(func=show_record, records_show_kind="job")

    records_export_parser = records_subparsers.add_parser(
        "export",
        help="Export records from a SQLite database",
    )
    records_export_subparsers = records_export_parser.add_subparsers(
        dest="records_export_kind"
    )

    customers_export_parser = records_export_subparsers.add_parser(
        "customers",
        help="Export CustomerRecord rows to JSON",
    )
    customers_export_parser.add_argument(
        "json_path",
        type=Path,
        help="Path for exported CustomerRecord JSON array",
    )
    customers_export_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    customers_export_parser.set_defaults(
        func=export_records,
        records_export_kind="customers",
    )

    jobs_export_parser = records_export_subparsers.add_parser(
        "jobs",
        help="Export JobRecord rows to JSON",
    )
    jobs_export_parser.add_argument(
        "json_path",
        type=Path,
        help="Path for exported JobRecord JSON array",
    )
    jobs_export_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    jobs_export_parser.set_defaults(func=export_records, records_export_kind="jobs")

    records_proposal_details_parser = records_subparsers.add_parser(
        "proposal-details",
        help="Inspect RecordProposalDetails JSON files",
    )
    records_proposal_details_subparsers = records_proposal_details_parser.add_subparsers(
        dest="records_proposal_details_command"
    )
    records_proposal_details_validate_parser = (
        records_proposal_details_subparsers.add_parser(
            "validate",
            help="Validate a RecordProposalDetails JSON file",
        )
    )
    records_proposal_details_validate_parser.add_argument(
        "details_json",
        type=Path,
        help="Path to RecordProposalDetails JSON",
    )
    records_proposal_details_validate_parser.set_defaults(
        func=validate_record_proposal_details
    )

    records_proposal_input_parser = records_subparsers.add_parser(
        "proposal-input",
        help="Compose ProposalInput JSON from records and proposal details",
    )
    records_proposal_input_parser.add_argument(
        "customer_id",
        help="Customer ID to use",
    )
    records_proposal_input_parser.add_argument(
        "job_id",
        help="Job ID to use",
    )
    records_proposal_input_parser.add_argument(
        "details_json",
        type=Path,
        help="Path to RecordProposalDetails JSON",
    )
    records_proposal_input_parser.add_argument(
        "output_json",
        type=Path,
        help="Path for composed ProposalInput JSON",
    )
    records_proposal_input_parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="SQLite database path",
    )
    records_proposal_input_parser.set_defaults(func=compose_record_proposal_input)

    return parser


def dev_status(args: argparse.Namespace) -> int:
    status = read_development_status(DEV_STATUS_PROJECT_STATE_PATH)
    if args.json:
        print(format_development_status_json(status))
    else:
        print(format_development_status(status))
    if not status.project_state_exists:
        print(
            f"Error: project-state file does not exist: {status.status_source_path}",
            file=sys.stderr,
        )
        return 1
    return 0


def load_proposal(path: Path) -> ProposalInput:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    try:
        return ProposalInput.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid proposal input in {path}: {exc}") from exc




def starter_a1_proposal_intake_payload() -> dict[str, Any]:
    return {
        "company_name": "A-1 Tank Removal LLC",
        "customer_name": "Jane Customer",
        "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
        "job_address": {
            "city_state_zip": "Milwaukee, WI 53202",
            "street_address": "123 Main St.",
        },
        "pricing_lines": [
            {
                "amount": "3000.00",
                "description": "Residential tank removal",
                "is_starting_at": True,
                "pricing_note": "Price is based on normal tank removal.",
            }
        ],
        "proposal_date": "2026-07-01",
        "scope_notes": [
            "Pump contents of tank (contents unknown)",
            "Open and clean tank",
            "Remove 1,000 gallon AST",
            "Remove and dispose of tank and residual contents",
        ],
        "special_notes": ["Customer is responsible for access to the tank area."],
    }


def customer_specific_a1_proposal_intake_payload(
    *,
    customer_name: str,
    street_address: str,
    city_state_zip: str,
) -> dict[str, Any]:
    return {
        "company_name": "A-1 Tank Removal LLC",
        "customer_name": customer_name,
        "item_description": "TODO: Replace with explicit item description.",
        "job_address": {
            "city_state_zip": city_state_zip,
            "street_address": street_address,
        },
        "pricing_lines": [
            {
                "amount": "1.00",
                "description": "TODO: Replace with explicit pricing description.",
                "is_starting_at": False,
                "pricing_note": "TODO: Replace with explicit pricing note or remove this note.",
            }
        ],
        "proposal_date": "2026-07-01",
        "scope_notes": ["TODO: Replace with explicit scope item."],
        "special_notes": ["TODO: Replace with explicit special note or remove this note."],
    }


def proposal_draft_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    customer_values = [args.customer_name, args.street_address, args.city_state_zip]
    if any(value is not None for value in customer_values):
        if not all(value is not None for value in customer_values):
            raise ValueError(
                "customer-specific draft requires --customer-name, "
                "--street-address, and --city-state-zip together"
            )
        return customer_specific_a1_proposal_intake_payload(
            customer_name=args.customer_name,
            street_address=args.street_address,
            city_state_zip=args.city_state_zip,
        )
    return starter_a1_proposal_intake_payload()


def create_proposal_draft_json(args: argparse.Namespace) -> int:
    output_path = args.output_json

    if output_path.exists() and not args.force:
        print(f"Error: proposal draft JSON already exists: {output_path}", file=sys.stderr)
        print("Use --force to overwrite it.", file=sys.stderr)
        return 1
    try:
        intake = a1_proposal_intake_from_dict(proposal_draft_payload_from_args(args))
        payload = intake.model_dump(mode="json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to write proposal draft JSON: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote proposal draft JSON: {output_path}")
    return 0


def customer_proposal_draft_from_args(args: argparse.Namespace) -> Any:
    customer = customer_record_from_json_file(args.customer_json)
    pricing_line = A1ProposalPricingLine(
        description=args.pricing_description,
        amount=args.pricing_amount,
        is_starting_at=args.starting_at,
        pricing_note=args.pricing_note,
    )
    return a1_proposal_intake_draft_from_customer_record(
        customer=customer,
        proposal_date=args.proposal_date,
        item_description=args.item_description,
        scope_notes=args.scope_note,
        pricing_lines=[pricing_line],
        special_notes=args.special_note,
        company_name=args.company_name,
    )


def create_customer_proposal_draft_json(args: argparse.Namespace) -> int:
    output_path = args.output_json

    if output_path.exists() and not args.force:
        print(
            f"Error: customer-backed proposal draft JSON already exists: {output_path}",
            file=sys.stderr,
        )
        print("Use --force to overwrite it.", file=sys.stderr)
        return 1
    try:
        intake = customer_proposal_draft_from_args(args)
        payload = intake.model_dump(mode="json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(
            f"Error: failed to write customer-backed proposal draft JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote customer-backed proposal draft JSON: {output_path}")
    return 0


def load_a1_proposal_intake(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"A-1 proposal intake JSON must be an object: {path}")

    try:
        return a1_proposal_intake_from_dict(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid A-1 proposal intake in {path}: {exc}") from exc

def generate_proposal(args: argparse.Namespace) -> int:
    input_path = args.input_json
    template_path = args.template
    output_path = args.output_docx

    if not input_path.exists():
        print(f"Error: JSON input file does not exist: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: JSON input path is not a file: {input_path}", file=sys.stderr)
        return 1
    if not _template_is_valid(template_path):
        return 1

    try:
        proposal = load_proposal(input_path)
        placeholder_paths = proposal_input_placeholder_paths(proposal)
        if placeholder_paths and not args.allow_placeholder_proposal_input:
            print(
                "Error: unresolved placeholder text in proposal input; "
                "refusing DOCX generation.",
                file=sys.stderr,
            )
            print(
                "Use --allow-placeholder-proposal-input to generate anyway.",
                file=sys.stderr,
            )
            print(
                "Placeholder fields: " + ", ".join(placeholder_paths),
                file=sys.stderr,
            )
            return 1
        result = DocxProposalRenderer().render(proposal, template_path, output_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to render proposal DOCX: {exc}", file=sys.stderr)
        return 1

    print(f"Generated proposal DOCX: {result}")
    return 0




UNRESOLVED_INTAKE_PLACEHOLDER_MARKERS = (
    "todo:",
    "replace with explicit",
)


def unresolved_a1_proposal_intake_placeholder_paths(intake: Any) -> list[str]:
    payload = intake.model_dump(mode="json")
    return _unresolved_placeholder_paths(payload)


def _unresolved_placeholder_paths(value: Any, path: str = "") -> list[str]:
    if isinstance(value, str):
        normalized = value.casefold()
        if any(marker in normalized for marker in UNRESOLVED_INTAKE_PLACEHOLDER_MARKERS):
            return [path or "<root>"]
        return []

    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            paths.extend(_unresolved_placeholder_paths(child, child_path))
        return paths

    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_unresolved_placeholder_paths(child, f"{path}[{index}]"))
        return paths

    return []

def generate_proposal_from_intake(args: argparse.Namespace) -> int:
    input_path = args.input_json
    template_path = args.template
    output_path = args.output_docx

    if not input_path.exists():
        print(
            f"Error: intake JSON input file does not exist: {input_path}",
            file=sys.stderr,
        )
        return 1
    if not input_path.is_file():
        print(
            f"Error: intake JSON input path is not a file: {input_path}",
            file=sys.stderr,
        )
        return 1
    if not _template_is_valid(template_path):
        return 1

    try:
        intake = load_a1_proposal_intake(input_path)
        placeholder_paths = unresolved_a1_proposal_intake_placeholder_paths(intake)
        if placeholder_paths and not args.allow_placeholder_intake:
            print(
                "Error: unresolved placeholder text in A-1 proposal intake; "
                "refusing DOCX generation.",
                file=sys.stderr,
            )
            print(
                "Use --allow-placeholder-intake to generate anyway.",
                file=sys.stderr,
            )
            print(
                "Placeholder fields: " + ", ".join(placeholder_paths),
                file=sys.stderr,
            )
            return 1
        proposal = intake.to_proposal_input()
        result = DocxProposalRenderer().render(proposal, template_path, output_path)
    except ValueError as exc:
        print(f"Error: invalid A-1 proposal intake JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(
            f"Error: failed to render proposal DOCX from intake: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Generated proposal DOCX: {result}")
    return 0

def validate_proposal(args: argparse.Namespace) -> int:
    input_path = args.input_json

    if not input_path.exists():
        print(f"Error: JSON input file does not exist: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: JSON input path is not a file: {input_path}", file=sys.stderr)
        return 1

    try:
        with input_path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
        proposal = ProposalInput.model_validate(data)
        placeholder_paths = proposal_input_placeholder_paths(proposal)
    except json.JSONDecodeError as exc:
        print(
            f"Error: invalid proposal input: Invalid JSON in {input_path}: {exc.msg}",
            file=sys.stderr,
        )
        return 1
    except ValidationError as exc:
        print(f"Error: invalid proposal input: {input_path}", file=sys.stderr)
        print("Validation errors:", file=sys.stderr)
        for error in _format_proposal_validation_errors(exc):
            print(f"- {error}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to validate proposal input: {exc}", file=sys.stderr)
        return 1

    print(f"ProposalInput validation passed: {input_path}")
    if placeholder_paths:
        print(
            "Warning: unresolved placeholder text in proposal input.",
            file=sys.stderr,
        )
        print(
            "Placeholder fields: " + ", ".join(placeholder_paths),
            file=sys.stderr,
        )
    return 0

def _format_proposal_validation_errors(exc: ValidationError) -> list[str]:
    return [_format_proposal_validation_error(error) for error in exc.errors()]


def _format_proposal_validation_error(error: dict[str, Any]) -> str:
    location_parts = error.get("loc", ())
    if location_parts:
        location = ".".join(str(part) for part in location_parts)
    else:
        location = "(root)"
    message = str(error.get("msg", "Invalid value"))
    return f"{location}: {message}"


def inspect_proposal(args: argparse.Namespace) -> int:
    input_path = args.input_json

    if not input_path.exists():
        print(f"Error: JSON input file does not exist: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: JSON input path is not a file: {input_path}", file=sys.stderr)
        return 1

    try:
        proposal = load_proposal(input_path)
        placeholder_paths = proposal_input_placeholder_paths(proposal)
    except ValueError as exc:
        print(f"Error: invalid proposal input: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to inspect proposal input: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = proposal.model_dump(mode="json")
        payload["placeholder_field_paths"] = placeholder_paths
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_proposal_summary(proposal)
        if placeholder_paths:
            print(
                "Warning: unresolved placeholder text in proposal input.",
                file=sys.stderr,
            )
            print(
                "Placeholder fields: " + ", ".join(placeholder_paths),
                file=sys.stderr,
            )
    return 0

def validate_proposal_intake(args: argparse.Namespace) -> int:
    input_path = args.input_json

    if not input_path.exists():
        error = f"intake JSON input file does not exist: {input_path}"
        if args.json:
            _print_proposal_intake_validation_json(input_path, error)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        error = f"intake JSON input path is not a file: {input_path}"
        if args.json:
            _print_proposal_intake_validation_json(input_path, error)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        intake = load_a1_proposal_intake(input_path)
        placeholder_paths = unresolved_a1_proposal_intake_placeholder_paths(intake)
    except ValueError as exc:
        error = str(exc)
        if args.json:
            _print_proposal_intake_validation_json(input_path, error)
        else:
            print(f"Error: invalid A-1 proposal intake JSON: {error}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        error = f"failed to validate proposal intake: {exc}"
        if args.json:
            _print_proposal_intake_validation_json(input_path, error)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.json:
        _print_proposal_intake_validation_json(
            input_path,
            None,
            placeholder_paths=placeholder_paths,
        )
    else:
        print(f"A-1 proposal intake validation passed: {input_path}")
        if placeholder_paths:
            print(
                "Warning: unresolved placeholder text in A-1 proposal intake.",
                file=sys.stderr,
            )
            print(
                "Placeholder fields: " + ", ".join(placeholder_paths),
                file=sys.stderr,
            )
    return 0

def _print_proposal_intake_validation_json(
    input_path: Path,
    error: str | None,
    *,
    placeholder_paths: list[str] | None = None,
) -> None:
    payload = _proposal_intake_validation_result_payload(
        input_path=input_path,
        valid=error is None,
        error=error,
        placeholder_paths=placeholder_paths or [],
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


def _proposal_intake_validation_result_payload(
    *,
    input_path: Path,
    valid: bool,
    error: str | None,
    placeholder_paths: list[str],
) -> dict[str, Any]:
    return {
        "error": error,
        "input_path": str(input_path),
        "placeholder_field_paths": placeholder_paths,
        "status": "valid" if valid else "invalid",
        "valid": valid,
    }

def normalize_proposal_intake(args: argparse.Namespace) -> int:
    input_path = args.input_json
    output_path = args.output_json

    if not input_path.exists():
        print(
            f"Error: intake JSON input file does not exist: {input_path}",
            file=sys.stderr,
        )
        return 1
    if not input_path.is_file():
        print(
            f"Error: intake JSON input path is not a file: {input_path}",
            file=sys.stderr,
        )
        return 1

    try:
        intake = load_a1_proposal_intake(input_path)
        proposal = intake.to_proposal_input()
        _write_proposal_input_json(proposal, output_path)
    except ValueError as exc:
        print(f"Error: invalid A-1 proposal intake JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to normalize proposal intake: {exc}", file=sys.stderr)
        return 1

    print(f"Normalized proposal intake JSON: {output_path}")
    return 0


def inspect_proposal_intake(args: argparse.Namespace) -> int:
    input_path = args.input_json

    if not input_path.exists():
        print(
            f"Error: intake JSON input file does not exist: {input_path}",
            file=sys.stderr,
        )
        return 1
    if not input_path.is_file():
        print(
            f"Error: intake JSON input path is not a file: {input_path}",
            file=sys.stderr,
        )
        return 1

    try:
        intake = load_a1_proposal_intake(input_path)
        placeholder_paths = unresolved_a1_proposal_intake_placeholder_paths(intake)
    except ValueError as exc:
        print(f"Error: invalid A-1 proposal intake JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to inspect proposal intake: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = _a1_proposal_intake_summary_payload(intake)
        payload["placeholder_field_paths"] = placeholder_paths
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_a1_proposal_intake_summary(intake)
        if placeholder_paths:
            print(
                "Warning: unresolved placeholder text in A-1 proposal intake.",
                file=sys.stderr,
            )
            print(
                "Placeholder fields: " + ", ".join(placeholder_paths),
                file=sys.stderr,
            )
    return 0

def list_capabilities(args: argparse.Namespace) -> int:
    capabilities = get_registered_plugin_capabilities()

    if args.json:
        payload = [capability.to_dict() for capability in capabilities]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    for index, capability in enumerate(capabilities):
        if index:
            print()
        print(capability.capability_id)
        print(f"plugin: {capability.plugin_id}")
        print(f"name: {capability.name}")
        print(f"category: {capability.category}")
        print(f"operation: {capability.operation_type.value}")
        print(f"risk: {capability.risk_level.value}")
    return 0


def show_task(args: argparse.Namespace) -> int:
    task_path = args.task_json

    if not task_path.exists():
        print(f"Error: TaskEnvelope JSON file does not exist: {task_path}", file=sys.stderr)
        return 1
    if not task_path.is_file():
        print(f"Error: TaskEnvelope JSON path is not a file: {task_path}", file=sys.stderr)
        return 1

    try:
        task = _load_task_json(task_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(task, indent=2, sort_keys=True))
        return 0

    requester = _as_dict(task.get("requester"))
    allowed_resources = _as_dict(task.get("allowed_resources"))
    verification_plan = _as_dict(task.get("verification_plan"))

    print(f"task_id: {task.get('task_id', '')}")
    print(f"title: {task.get('title', '')}")
    print(f"status: {task.get('status', '')}")
    print(f"priority: {task.get('priority', '')}")
    print(f"requester: {requester.get('type', '')} {requester.get('id', '')}")
    _print_list("allowed capabilities", _as_list(allowed_resources.get("capabilities")))
    _print_list("context refs", _as_list(task.get("context_refs")))
    _print_list(
        "verification evidence required",
        _as_list(verification_plan.get("evidence_required")),
    )
    return 0


def validate_task(args: argparse.Namespace) -> int:
    task_path = args.task_json

    if not task_path.exists():
        print(f"Error: TaskEnvelope JSON file does not exist: {task_path}", file=sys.stderr)
        return 1
    if not task_path.is_file():
        print(f"Error: TaskEnvelope JSON path is not a file: {task_path}", file=sys.stderr)
        return 1

    try:
        task = _load_task_json(task_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    issues = _validate_task_envelope(task)
    if issues:
        for issue in issues:
            print(f"Validation error: {issue}", file=sys.stderr)
        return 1

    print(f"TaskEnvelope validation passed: {task.get('task_id', '')}")
    return 0


def inspect_workflow_plan(args: argparse.Namespace) -> int:
    plan_path = args.plan_json

    if not plan_path.exists():
        print(f"Error: WorkflowPlan JSON file does not exist: {plan_path}", file=sys.stderr)
        return 1
    if not plan_path.is_file():
        print(f"Error: WorkflowPlan JSON path is not a file: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = _load_workflow_plan(plan_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_workflow_plan_summary(plan)
    return 0


def inspect_workflow_plan_review(args: argparse.Namespace) -> int:
    review_path = args.review_json

    if not review_path.exists():
        print(
            f"Error: WorkflowPlanReview JSON file does not exist: {review_path}",
            file=sys.stderr,
        )
        return 1
    if not review_path.is_file():
        print(
            f"Error: WorkflowPlanReview JSON path is not a file: {review_path}",
            file=sys.stderr,
        )
        return 1

    try:
        review = _load_workflow_plan_review(review_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_workflow_plan_review_summary(review)
    return 0


def import_records(args: argparse.Namespace) -> int:
    input_path = args.json_path

    if not input_path.exists():
        print(f"Error: record JSON file does not exist: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"Error: record JSON path is not a file: {input_path}", file=sys.stderr)
        return 1

    try:
        store = create_sqlite_record_store(args.db)
        if args.records_import_kind == "customer":
            customer = import_customer_record_file(store, input_path)
            print(f"Imported customer: {customer.customer_id}")
        elif args.records_import_kind == "job":
            job = import_job_record_file(store, input_path)
            print(f"Imported job: {job.job_id}")
        elif args.records_import_kind == "customers":
            customers = import_customer_records_file(store, input_path)
            print(f"Imported customers: {len(customers)}")
        elif args.records_import_kind == "jobs":
            jobs = import_job_records_file(store, input_path)
            print(f"Imported jobs: {len(jobs)}")
        else:
            print(
                f"Error: unsupported records import kind: {args.records_import_kind}",
                file=sys.stderr,
            )
            return 1
    except (ValueError, ValidationError) as exc:
        print(f"Error: failed to import records: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to import records: {exc}", file=sys.stderr)
        return 1

    return 0


def list_records(args: argparse.Namespace) -> int:
    store = create_sqlite_record_store(args.db)

    if args.records_list_kind == "customers":
        customers = store.customers.list_customers()
        if args.json:
            print(customer_records_to_json(customers))
        elif customers:
            for customer in customers:
                print(f"{customer.customer_id}\t{customer.display_name}")
        else:
            print("No customers found.")
        return 0

    if args.records_list_kind == "jobs":
        jobs = store.jobs.list_jobs()
        if args.json:
            print(job_records_to_json(jobs))
        elif jobs:
            for job in jobs:
                print(
                    f"{job.job_id}\t{job.customer_id}\t"
                    f"{job.job_name}\t{job.status.value}"
                )
        else:
            print("No jobs found.")
        return 0

    print(f"Error: unsupported records list kind: {args.records_list_kind}", file=sys.stderr)
    return 1


def show_record(args: argparse.Namespace) -> int:
    store = create_sqlite_record_store(args.db)

    if args.records_show_kind == "customer":
        customer = store.customers.get_customer(args.customer_id)
        if customer is None:
            print(f"Customer not found: {args.customer_id}", file=sys.stderr)
            return 1
        if args.json:
            print(customer_record_to_json(customer))
        else:
            print(f"customer_id: {customer.customer_id}")
            print(f"display_name: {customer.display_name}")
            _print_optional_value("phone", customer.phone)
            _print_optional_value("email", customer.email)
            _print_optional_value(
                "billing_street_address",
                customer.billing_street_address,
            )
            _print_optional_value(
                "billing_city_state_zip",
                customer.billing_city_state_zip,
            )
            _print_list_if_present("notes", customer.notes)
        return 0

    if args.records_show_kind == "job":
        job = store.jobs.get_job(args.job_id)
        if job is None:
            print(f"Job not found: {args.job_id}", file=sys.stderr)
            return 1
        if args.json:
            print(job_record_to_json(job))
        else:
            print(f"job_id: {job.job_id}")
            print(f"customer_id: {job.customer_id}")
            print(f"job_name: {job.job_name}")
            print(f"site_street_address: {job.site_street_address}")
            print(f"site_city_state_zip: {job.site_city_state_zip}")
            print(f"status: {job.status.value}")
            print(f"tank_location_type: {job.tank_location_type.value}")
            _print_optional_value("tank_size_gallons", job.tank_size_gallons)
            _print_optional_value("tank_contents", job.tank_contents)
            print(f"contents_known: {job.contents_known}")
            _print_list_if_present("scope_notes", job.scope_notes)
            _print_list_if_present("internal_notes", job.internal_notes)
        return 0

    print(f"Error: unsupported records show kind: {args.records_show_kind}", file=sys.stderr)
    return 1


def export_records(args: argparse.Namespace) -> int:
    try:
        store = create_sqlite_record_store(args.db)
        if args.records_export_kind == "customers":
            count = len(store.customers.list_customers())
            output_path = export_customer_records_file(store, args.json_path)
            print(f"Exported customers: {count} -> {output_path}")
        elif args.records_export_kind == "jobs":
            count = len(store.jobs.list_jobs())
            output_path = export_job_records_file(store, args.json_path)
            print(f"Exported jobs: {count} -> {output_path}")
        else:
            print(
                f"Error: unsupported records export kind: {args.records_export_kind}",
                file=sys.stderr,
            )
            return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to export records: {exc}", file=sys.stderr)
        return 1

    return 0


def validate_record_proposal_details(args: argparse.Namespace) -> int:
    details_path = args.details_json

    if not details_path.exists():
        print(
            f"Error: RecordProposalDetails JSON file does not exist: {details_path}",
            file=sys.stderr,
        )
        return 1
    if not details_path.is_file():
        print(
            f"Error: RecordProposalDetails JSON path is not a file: {details_path}",
            file=sys.stderr,
        )
        return 1

    try:
        record_proposal_details_from_file(details_path)
    except (ValueError, ValidationError) as exc:
        print(f"Error: invalid RecordProposalDetails JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to validate RecordProposalDetails JSON: {exc}", file=sys.stderr)
        return 1

    print(f"RecordProposalDetails validation passed: {details_path}")
    return 0


def compose_record_proposal_input(args: argparse.Namespace) -> int:
    try:
        store = create_sqlite_record_store(args.db)
        customer = store.customers.get_customer(args.customer_id)
        if customer is None:
            print(f"Customer not found: {args.customer_id}", file=sys.stderr)
            return 1

        job = store.jobs.get_job(args.job_id)
        if job is None:
            print(f"Job not found: {args.job_id}", file=sys.stderr)
            return 1

        details = record_proposal_details_from_file(args.details_json)
        proposal = create_proposal_input_from_record_details(
            customer=customer,
            job=job,
            details=details,
        )
        _write_proposal_input_json(proposal, args.output_json)
    except (ValueError, ValidationError) as exc:
        print(f"Error: failed to compose proposal input: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to compose proposal input: {exc}", file=sys.stderr)
        return 1

    print(f"Composed proposal input JSON: {args.output_json}")
    return 0


def intake_proposal(args: argparse.Namespace) -> int:
    template_path = args.template
    output_path = args.output
    json_output_path = args.json_output

    if not _template_is_valid(template_path):
        return 1

    try:
        proposal = collect_proposal_input()
        if json_output_path is not None:
            _write_proposal_json(proposal, json_output_path)
        result = DocxProposalRenderer().render(proposal, template_path, output_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to render proposal DOCX: {exc}", file=sys.stderr)
        return 1

    if json_output_path is not None:
        print(f"Wrote proposal JSON: {json_output_path}")
    print(f"Generated proposal DOCX: {result}")
    return 0


def _load_task_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"TaskEnvelope JSON must be an object: {path}")
    return data


def _load_workflow_plan(path: Path) -> WorkflowPlan:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    try:
        return WorkflowPlan.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid WorkflowPlan in {path}: {exc}") from exc


def _load_workflow_plan_review(path: Path) -> WorkflowPlanReview:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    try:
        return WorkflowPlanReview.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid WorkflowPlanReview in {path}: {exc}") from exc


def _validate_task_envelope(task: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required_fields = [
        "task_id",
        "title",
        "status",
        "priority",
        "requester",
        "source",
        "context_refs",
        "allowed_resources",
        "verification_plan",
    ]
    for field_name in required_fields:
        if field_name not in task:
            issues.append(f"Missing required field: {field_name}")

    requester = task.get("requester")
    if "requester" in task:
        if not isinstance(requester, dict):
            issues.append("requester must be an object")
        else:
            for field_name in ["type", "id"]:
                if field_name not in requester:
                    issues.append(f"Missing requester field: {field_name}")

    allowed_resources = task.get("allowed_resources")
    if "allowed_resources" in task:
        if not isinstance(allowed_resources, dict):
            issues.append("allowed_resources must be an object")
        else:
            capabilities = allowed_resources.get("capabilities")
            if "capabilities" not in allowed_resources:
                issues.append("Missing allowed_resources field: capabilities")
            elif not isinstance(capabilities, list):
                issues.append("allowed_resources.capabilities must be a list")
            else:
                registered_capability_ids = {
                    capability.capability_id
                    for capability in get_registered_plugin_capabilities()
                }
                for capability_id in capabilities:
                    if capability_id not in registered_capability_ids:
                        issues.append(f"Unknown capability id: {capability_id}")

    if "context_refs" in task and not isinstance(task.get("context_refs"), list):
        issues.append("context_refs must be a list")

    verification_plan = task.get("verification_plan")
    if "verification_plan" in task:
        if not isinstance(verification_plan, dict):
            issues.append("verification_plan must be an object")
        else:
            evidence_required = verification_plan.get("evidence_required")
            if "evidence_required" not in verification_plan:
                issues.append("Missing verification_plan field: evidence_required")
            elif not isinstance(evidence_required, list):
                issues.append("verification_plan.evidence_required must be a list")

    return issues


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_yes_no_or_not_available(value: bool | None) -> str:
    if value is None:
        return "not available"
    return _format_yes_no(value)


def _print_list(label: str, values: list[Any]) -> None:
    print(f"{label}:")
    if not values:
        print("  - (none)")
        return
    for value in values:
        print(f"  - {value}")


def _print_optional_value(label: str, value: object | None) -> None:
    if value is not None:
        print(f"{label}: {value}")


def _print_list_if_present(label: str, values: list[str]) -> None:
    if values:
        _print_list(label, values)


def _print_proposal_summary(proposal: ProposalInput) -> None:
    print(f"Customer: {proposal.customer_name}")
    print(f"Site Address: {proposal.street_address}, {proposal.city_state_zip}")
    print(f"Item Description: {proposal.item_description}")
    print(f"Scope Items: {len(proposal.scope_items)}")
    print("Pricing Lines: 1")
    print(f"Total: {_format_proposal_total(proposal)}")
    print(f"Notes: {'present' if proposal.notes else 'none'}")
    if proposal.company_config.company_name:
        print(f"Company: {proposal.company_config.company_name}")


def _a1_proposal_intake_summary_payload(intake: Any) -> dict[str, Any]:
    pricing_line = intake.pricing_lines[0]
    return {
        "customer_name": intake.customer_name,
        "is_starting_at": pricing_line.is_starting_at,
        "item_description": intake.item_description,
        "job_address": {
            "city_state_zip": intake.job_address.city_state_zip,
            "street_address": intake.job_address.street_address,
        },
        "notes_count": len(intake.special_notes),
        "pricing_amount": f"{pricing_line.amount:.2f}",
        "proposal_date": intake.proposal_date.isoformat(),
        "scope_count": len(intake.scope_notes),
    }


def _print_a1_proposal_intake_summary(intake: Any) -> None:
    pricing_line = intake.pricing_lines[0]
    print(f"Customer: {intake.customer_name}")
    print(
        "Job Address: "
        f"{intake.job_address.street_address}, {intake.job_address.city_state_zip}"
    )
    print(f"Proposal Date: {intake.proposal_date.isoformat()}")
    print(f"Item Description: {intake.item_description}")
    print(f"Scope Count: {len(intake.scope_notes)}")
    print(f"Pricing Amount: ${pricing_line.amount:,.2f}")
    print(f"Starting At: {_format_yes_no(pricing_line.is_starting_at)}")
    print(f"Notes Count: {len(intake.special_notes)}")


def _print_workflow_plan_summary(plan: WorkflowPlan) -> None:
    print(f"Workflow plan: {plan.workflow_name}")
    print(f"Status: {plan.status.value}")
    if plan.description:
        print(f"Description: {plan.description}")
    print(f"Approval required: {_format_yes_no(plan.approval_required)}")
    print(f"Approval approved: {_format_yes_no(plan.approval.approved)}")
    print(f"Steps: {len(plan.steps)}")
    print(
        "Steps requiring human review: "
        f"{sum(1 for step in plan.steps if step.requires_human_review)}"
    )
    print(f"Artifact-writing steps: {sum(1 for step in plan.steps if step.writes_artifact)}")
    print("Step names:")
    for step in plan.steps:
        print(f"  {step.step_number}. {step.name}")
    print("Execution: not supported")


def _print_workflow_plan_review_summary(review: WorkflowPlanReview) -> None:
    print(f"Workflow review: {review.workflow_name}")
    print(f"Review decision: {review.decision.value}")
    print(f"Approved for execution: {_format_yes_no(review.approved_for_execution)}")
    print(f"Reviewer: {review.reviewed_by}")
    if review.review_notes:
        print(f"Review notes: {review.review_notes}")
    else:
        print("Review notes: none")
    print("Execution: not supported")
    print("Approval mutation: not supported")


def _format_proposal_total(proposal: ProposalInput) -> str:
    amount = f"${proposal.pricing.amount:,.2f}"
    if proposal.pricing.is_starting_at:
        return f"{proposal.company_config.starting_at_label} {amount}"
    return amount


def _template_is_valid(template_path: Path) -> bool:
    if not template_path.exists():
        print(f"Error: DOCX template file does not exist: {template_path}", file=sys.stderr)
        return False
    if not template_path.is_file():
        print(f"Error: DOCX template path is not a file: {template_path}", file=sys.stderr)
        return False
    return True


def _write_proposal_json(proposal: ProposalInput, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{proposal.model_dump_json(indent=2)}\n", encoding="utf-8")


def _write_proposal_input_json(proposal: ProposalInput, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = proposal.model_dump(mode="json")
    output_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


_ORIGINAL_BUILD_PARSER = build_parser


def build_parser() -> argparse.ArgumentParser:
    parser = _ORIGINAL_BUILD_PARSER()
    orchestration_parser = _get_subparser(parser, "orchestration")
    orchestration_subparsers = _get_subparsers_action(orchestration_parser)
    preflight_parser = orchestration_subparsers.add_parser(
        "preflight",
        help="Inspect workflow plan preflight reports",
    )
    preflight_subparsers = preflight_parser.add_subparsers(
        dest="orchestration_preflight_command"
    )
    preflight_inspect_parser = preflight_subparsers.add_parser(
        "inspect",
        help="Inspect a WorkflowPlan and WorkflowPlanReview without executing them",
    )
    preflight_inspect_parser.add_argument(
        "plan_json",
        type=Path,
        help="Path to serialized WorkflowPlan JSON",
    )
    preflight_inspect_parser.add_argument(
        "review_json",
        type=Path,
        help="Path to serialized WorkflowPlanReview JSON",
    )
    preflight_inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the preflight report as JSON",
    )
    preflight_inspect_parser.set_defaults(func=inspect_workflow_preflight)
    return parser


def inspect_workflow_preflight(args: argparse.Namespace) -> int:
    plan_path = args.plan_json
    review_path = args.review_json

    if not plan_path.exists():
        print(f"Error: WorkflowPlan JSON file does not exist: {plan_path}", file=sys.stderr)
        return 1
    if not plan_path.is_file():
        print(f"Error: WorkflowPlan JSON path is not a file: {plan_path}", file=sys.stderr)
        return 1
    if not review_path.exists():
        print(
            f"Error: WorkflowPlanReview JSON file does not exist: {review_path}",
            file=sys.stderr,
        )
        return 1
    if not review_path.is_file():
        print(
            f"Error: WorkflowPlanReview JSON path is not a file: {review_path}",
            file=sys.stderr,
        )
        return 1

    try:
        plan = _load_workflow_plan(plan_path)
        review = _load_workflow_plan_review(review_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    from phoenix_office.orchestration import run_orchestration_preflight

    report = run_orchestration_preflight(plan, review)
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        _print_workflow_preflight_summary(report)
    return 0


def _print_workflow_preflight_summary(report: Any) -> None:
    print(f"Orchestration preflight: {report.plan_workflow_name}")
    print(f"Plan workflow: {report.plan_workflow_name}")
    print(f"Plan fingerprint: {report.plan_fingerprint}")
    print(
        "Reviewed plan fingerprint: "
        f"{report.reviewed_plan_fingerprint or 'not available'}"
    )
    print(
        "Plan fingerprint matches review: "
        f"{_format_yes_no_or_not_available(report.plan_fingerprint_matches_review)}"
    )
    print(f"Review workflow: {report.review_workflow_name}")
    print(f"Review decision: {report.review_decision.value}")
    print(f"Approved for execution: {_format_yes_no(report.approved_for_execution)}")
    print(f"Execution available: {_format_yes_no(report.execution_available)}")
    print(f"Execution message: {report.execution_message}")
    print(f"Blocking issues: {_format_yes_no(report.has_blocking_issues)}")
    print("Issues:")
    if not report.issues:
        print("  - (none)")
    else:
        for issue in report.issues:
            print(f"  - {issue.code}: {issue.message}")
    print("Execution: not supported")


def _get_subparsers_action(parser: argparse.ArgumentParser) -> argparse.Action:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("parser does not define subcommands")


def _get_subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    subparsers_action = _get_subparsers_action(parser)
    subparser = subparsers_action.choices.get(name)
    if subparser is None:
        raise RuntimeError(f"parser does not define subcommand: {name}")
    return subparser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
