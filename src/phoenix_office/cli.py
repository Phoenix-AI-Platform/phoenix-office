"""Command-line interface for Phoenix Office."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from docx import Document
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
    codex_handoff_parser = dev_subparsers.add_parser(
        "codex-handoff",
        help="Inspect a read-only Codex handoff package",
    )
    codex_handoff_parser.add_argument(
        "handoff_json",
        type=Path,
        help="Path to CodexHandoffPackage JSON",
    )
    codex_handoff_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the validated Codex handoff package as JSON",
    )
    codex_handoff_parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Output only the validated Codex handoff package prompt",
    )
    codex_handoff_parser.set_defaults(func=inspect_codex_handoff)
    codex_invocation_preflight_parser = dev_subparsers.add_parser(
        "codex-invocation-preflight",
        help="Run a read-only static Codex invocation preflight",
    )
    codex_invocation_preflight_parser.add_argument(
        "handoff_json",
        type=Path,
        help="Path to CodexHandoffPackage JSON",
    )
    codex_invocation_preflight_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the static preflight report as JSON",
    )
    codex_invocation_preflight_parser.set_defaults(
        func=codex_invocation_preflight
    )
    codex_invocation_request_parser = dev_subparsers.add_parser(
        "codex-invocation-request",
        help="Draft a read-only supervised Codex invocation request",
    )
    codex_invocation_request_parser.add_argument(
        "handoff_json",
        type=Path,
        help="Path to CodexHandoffPackage JSON",
    )
    codex_invocation_request_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the deterministic request draft as JSON",
    )
    codex_invocation_request_parser.set_defaults(
        func=codex_invocation_request
    )
    codex_runtime_probe_parser = dev_subparsers.add_parser(
        "codex-runtime-probe",
        help="Probe local read-only Codex CLI runtime capabilities",
    )
    codex_runtime_probe_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the runtime capability probe report as JSON",
    )
    codex_runtime_probe_parser.set_defaults(func=codex_runtime_probe)
    codex_pilot_evidence_parser = dev_subparsers.add_parser(
        "codex-pilot-evidence",
        help="Inspect supervised Codex pilot evidence package completeness",
    )
    codex_pilot_evidence_parser.add_argument(
        "evidence_json",
        type=Path,
        help="Path to Codex pilot evidence package JSON",
    )
    codex_pilot_evidence_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the evidence inspection report as JSON",
    )
    codex_pilot_evidence_parser.set_defaults(func=codex_pilot_evidence)
    codex_pilot_preflight_parser = dev_subparsers.add_parser(
        "codex-pilot-preflight",
        help="Run the read-only supervised Codex pilot readiness preflight",
    )
    codex_pilot_preflight_parser.add_argument(
        "handoff_json",
        type=Path,
        help="Path to CodexHandoffPackage JSON",
    )
    codex_pilot_preflight_parser.add_argument(
        "evidence_json",
        type=Path,
        help="Path to Codex pilot evidence package JSON",
    )
    codex_pilot_preflight_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the composite pilot preflight report as JSON",
    )
    codex_pilot_preflight_parser.set_defaults(func=codex_pilot_preflight)
    codex_pilot_authorization_parser = dev_subparsers.add_parser(
        "codex-pilot-authorization",
        help="Inspect a read-only supervised Codex pilot authorization packet",
    )
    codex_pilot_authorization_parser.add_argument(
        "handoff_json",
        type=Path,
        help="Path to CodexHandoffPackage JSON",
    )
    codex_pilot_authorization_parser.add_argument(
        "evidence_json",
        type=Path,
        help="Path to Codex pilot evidence package JSON",
    )
    codex_pilot_authorization_parser.add_argument(
        "authorization_json",
        type=Path,
        help="Path to Codex pilot authorization packet JSON",
    )
    codex_pilot_authorization_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the authorization packet inspection report as JSON",
    )
    codex_pilot_authorization_parser.set_defaults(
        func=codex_pilot_authorization
    )

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

    readiness_proposal_parser = proposal_subparsers.add_parser(
        "readiness",
        help="Check whether a proposal JSON input is ready for DOCX generation",
    )
    readiness_proposal_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to proposal JSON input",
    )
    readiness_proposal_parser.add_argument(
        "--json",
        action="store_true",
        help="Output proposal readiness as JSON",
    )
    readiness_proposal_parser.set_defaults(func=check_proposal_readiness)

    template_readiness_parser = proposal_subparsers.add_parser(
        "template-readiness",
        help="Check whether a DOCX proposal template path is usable",
    )
    template_readiness_parser.add_argument(
        "template_docx",
        type=Path,
        help="Path to DOCX proposal template",
    )
    template_readiness_parser.add_argument(
        "--json",
        action="store_true",
        help="Output template readiness as JSON",
    )
    template_readiness_parser.set_defaults(func=check_proposal_template_readiness)

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
    intake_readiness_parser = proposal_subparsers.add_parser(
        "intake-readiness",
        help="Check whether an A-1 intake JSON file is ready for normalization",
    )
    intake_readiness_parser.add_argument(
        "input_json",
        type=Path,
        help="Path to A-1 proposal intake JSON input",
    )
    intake_readiness_parser.add_argument(
        "--json",
        action="store_true",
        help="Output A-1 intake readiness as JSON",
    )
    intake_readiness_parser.set_defaults(func=check_proposal_intake_readiness)
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


def inspect_codex_handoff(args: argparse.Namespace) -> int:
    package_path = args.handoff_json

    if args.json and args.prompt_only:
        print(
            "Error: --prompt-only cannot be combined with --json",
            file=sys.stderr,
        )
        return 1

    if not package_path.exists():
        message = f"CodexHandoffPackage JSON file does not exist: {package_path}"
        if args.json:
            _print_codex_handoff_json_failure(
                error_code="missing_file",
                message=message,
                path=package_path,
            )
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1
    if not package_path.is_file():
        message = f"CodexHandoffPackage JSON path is not a file: {package_path}"
        if args.json:
            _print_codex_handoff_json_failure(
                error_code="not_file",
                message=message,
                path=package_path,
            )
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    try:
        package = _load_codex_handoff_package_json(package_path)
    except ValueError as exc:
        if args.json:
            _print_codex_handoff_json_failure(
                error_code="invalid_json",
                message=str(exc),
                path=package_path,
            )
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        message = f"failed to read CodexHandoffPackage JSON: {exc}"
        if args.json:
            _print_codex_handoff_json_failure(
                error_code="read_error",
                message=message,
                path=package_path,
            )
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    issues = _validate_codex_handoff_package(package)
    if issues:
        if args.json:
            _print_codex_handoff_json_failure(
                error_code="unsafe_or_invalid_package",
                message="unsafe or invalid CodexHandoffPackage",
                path=package_path,
                issues=issues,
            )
        else:
            print("Error: unsafe or invalid CodexHandoffPackage.", file=sys.stderr)
            for issue in issues:
                print(f"- {issue}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(package, indent=2, sort_keys=True))
    elif args.prompt_only:
        print(package["prompt"])
    else:
        _print_codex_handoff_summary(package)
    return 0


def codex_invocation_preflight(args: argparse.Namespace) -> int:
    package, report = _load_codex_invocation_preflight(args.handoff_json)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_codex_invocation_preflight_report(report)

    return 0 if report["static_eligible"] else 1


def codex_invocation_request(args: argparse.Namespace) -> int:
    package, preflight_report = _load_codex_invocation_preflight(args.handoff_json)
    if package is None or not preflight_report["static_eligible"]:
        failure = _build_codex_invocation_request_failure_report(
            path=args.handoff_json,
            preflight_report=preflight_report,
        )
        if args.json:
            print(json.dumps(failure, indent=2, sort_keys=True))
        else:
            _print_codex_invocation_request_failure(failure)
        return 1

    request = _build_codex_invocation_request_draft(
        package=package,
        preflight_report=preflight_report,
    )
    if args.json:
        print(json.dumps(request, indent=2, sort_keys=True))
    else:
        _print_codex_invocation_request_draft(request)
    return 0


def codex_runtime_probe(args: argparse.Namespace) -> int:
    report = _run_codex_runtime_probe()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_codex_runtime_probe(report)
    return 0 if report["local_cli_ready"] else 1


def codex_pilot_evidence(args: argparse.Namespace) -> int:
    report = _inspect_codex_pilot_evidence_package(args.evidence_json)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_codex_pilot_evidence_report(report)
    return 0 if report["evidence_package_complete"] else 1


def codex_pilot_preflight(args: argparse.Namespace) -> int:
    report = _run_codex_pilot_preflight(
        handoff_path=args.handoff_json,
        evidence_path=args.evidence_json,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_codex_pilot_preflight_report(report)
    return 0 if report["eligible_for_authorization_review"] else 1


def codex_pilot_authorization(args: argparse.Namespace) -> int:
    report = _run_codex_pilot_authorization(
        handoff_path=args.handoff_json,
        evidence_path=args.evidence_json,
        authorization_path=args.authorization_json,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_codex_pilot_authorization_report(report)
    return 0 if report["authorization_packet_valid_for_one_attempt"] else 1


def _load_codex_invocation_preflight(
    package_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    package: dict[str, Any] | None = None
    package_blockers: list[str] = []

    if not package_path.exists():
        package_blockers.append(
            f"CodexHandoffPackage JSON file does not exist: {package_path}"
        )
    elif not package_path.is_file():
        package_blockers.append(
            f"CodexHandoffPackage JSON path is not a file: {package_path}"
        )
    else:
        try:
            package = _load_codex_handoff_package_json(package_path)
        except ValueError as exc:
            package_blockers.append(str(exc))
        except OSError as exc:
            package_blockers.append(
                f"failed to read CodexHandoffPackage JSON: {exc}"
            )

    if package is not None:
        package_blockers.extend(
            _validate_codex_invocation_preflight_package(package)
        )

    report = _build_codex_invocation_preflight_report(
        package=package,
        path=package_path,
        package_blockers=package_blockers,
    )
    return package, report


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


def check_proposal_readiness(args: argparse.Namespace) -> int:
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
        print(f"Error: failed to check proposal readiness: {exc}", file=sys.stderr)
        return 1

    ready = not placeholder_paths
    payload = {
        "blocker_field_paths": placeholder_paths,
        "input_path": str(input_path),
        "ready_for_docx_generation": ready,
        "status": "ready" if ready else "blocked",
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ready:
        print(f"ProposalInput readiness: ready ({input_path})")
        print("Ready for DOCX generation: yes")
        print(
            "Next manual command: "
            "python -m phoenix_office.cli proposal generate "
            f"{input_path} output/proposal.docx "
            "--template tests/fixtures/templates/a1_proposal_template.docx"
        )
    else:
        print(f"ProposalInput readiness: blocked ({input_path})")
        print("Ready for DOCX generation: no")
        print("Blocker fields: " + ", ".join(placeholder_paths))

    return 0 if ready else 1


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


def check_proposal_template_readiness(args: argparse.Namespace) -> int:
    template_path = args.template_docx
    error: str | None = None

    if not template_path.exists():
        error = f"DOCX template file does not exist: {template_path}"
    elif not template_path.is_file():
        error = f"DOCX template path is not a file: {template_path}"
    else:
        try:
            Document(str(template_path))
        except Exception as exc:  # noqa: BLE001 - python-docx exposes broad parse errors.
            error = f"DOCX template could not be opened: {exc}"

    ready = error is None
    payload = {
        "error": error,
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "template_path": str(template_path),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ready:
        print(f"DOCX template readiness: ready ({template_path})")
        print("Ready for proposal generation: yes")
    else:
        print(f"DOCX template readiness: blocked ({template_path})")
        print("Ready for proposal generation: no")
        print(f"Blocker: {error}")

    return 0 if ready else 1


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


def check_proposal_intake_readiness(args: argparse.Namespace) -> int:
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
        print(f"Error: failed to check proposal intake readiness: {exc}", file=sys.stderr)
        return 1

    ready = not placeholder_paths
    payload = {
        "blocker_field_paths": placeholder_paths,
        "input_path": str(input_path),
        "ready_for_normalization": ready,
        "status": "ready" if ready else "blocked",
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ready:
        print(f"A-1 proposal intake readiness: ready ({input_path})")
        print("Ready for normalization: yes")
        print(
            "Next manual command: "
            "python -m phoenix_office.cli proposal intake-normalize "
            f"{input_path} output/a1_proposal_input.json"
        )
    else:
        print(f"A-1 proposal intake readiness: blocked ({input_path})")
        print("Ready for normalization: no")
        print("Blocker fields: " + ", ".join(placeholder_paths))

    return 0 if ready else 1


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


def _load_codex_handoff_package_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data: Any = json.load(file)
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid UTF-8 in {path}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"CodexHandoffPackage JSON must be an object: {path}")
    return data


def _print_codex_handoff_json_failure(
    *,
    error_code: str,
    message: str,
    path: Path,
    issues: list[str] | None = None,
) -> None:
    payload = {
        "error_code": error_code,
        "issues": issues or [],
        "message": message,
        "ok": False,
        "path": str(path),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


CODEX_RUNTIME_PROBE_SCHEMA_VERSION = "codex-runtime-probe.v1"
CODEX_RUNTIME_PROBE_TIMEOUT_SECONDS = 5
CODEX_RUNTIME_VERSION_ARGV = ["codex", "--version"]
CODEX_RUNTIME_EXEC_HELP_ARGV = ["codex", "exec", "--help"]
CODEX_RUNTIME_EXTERNAL_CHECKS_REQUIRED = [
    "authentication and runner access",
    "enforceable per-run budget ceiling",
    "operator cancellation behavior",
    "GitHub branch and PR permissions",
    "duplicate active-PR detection",
    "branch-collision detection",
    "actual Codex availability during a task",
    "final CI",
    "assistant review",
]
CODEX_RUNTIME_CAPABILITY_FIELDS = {
    "non_interactive_exec_detected": "non-interactive codex exec evidence",
    "stdin_prompt_input_detected": "stdin or '-' prompt input support",
    "ephemeral_option_detected": "--ephemeral option",
    "sandbox_option_detected": "--sandbox option",
    "working_directory_option_detected": "--cd or -C option",
    "json_option_detected": "--json option",
    "output_last_message_option_detected": "--output-last-message or -o option",
    "explicit_budget_option_detected": "explicit per-run budget option",
}


CODEX_PILOT_EVIDENCE_SCHEMA_VERSION = "codex-pilot-evidence.v1"
CODEX_PILOT_EVIDENCE_REPOSITORY = "Phoenix-AI-Platform/phoenix-office"
CODEX_PILOT_EVIDENCE_KIND = "docs-only-supervised"
CODEX_PILOT_EVIDENCE_COMMAND = "dev codex-pilot-evidence"
CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS = {
    "authentication_runner_access": "human_operator",
    "per_run_budget_ceiling": "human_operator_and_assistant_reviewer",
    "operator_cancellation_timeout": "human_operator",
    "github_branch_creation_permission": "human_operator",
    "github_pr_creation_permission": "human_operator_and_assistant_reviewer",
    "codex_cannot_approve_or_merge": "assistant_reviewer",
    "duplicate_active_pr_detection": "assistant_reviewer",
    "branch_collision_detection": "assistant_reviewer",
    "codex_task_time_availability": "human_operator",
    "final_ci_requirement": "assistant_reviewer",
    "assistant_architecture_review": "assistant_reviewer",
}
CODEX_PILOT_EVIDENCE_CONTROL_IDS = list(
    CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
)
CODEX_PILOT_EVIDENCE_STATUSES = {"verified", "blocked", "unverified"}
CODEX_PILOT_EVIDENCE_REVIEWER_ROLES = {
    "human_operator",
    "assistant_reviewer",
    "human_operator_and_assistant_reviewer",
}
CODEX_PILOT_EVIDENCE_PACKAGE_FIELDS = {
    "schema_version",
    "repository",
    "pilot_kind",
    "handoff_id",
    "controls",
    "pilot_ready",
    "invocation_authorized",
}
CODEX_PILOT_EVIDENCE_CONTROL_FIELDS = {
    "control_id",
    "status",
    "evidence_ref",
    "reviewer_role",
}


CODEX_PILOT_PREFLIGHT_SCHEMA_VERSION = "codex-pilot-preflight.v1"
CODEX_PILOT_PREFLIGHT_COMMAND = "dev codex-pilot-preflight"
CODEX_PILOT_AUTHORIZATION_SCHEMA_VERSION = "codex-pilot-authorization.v1"
CODEX_PILOT_AUTHORIZATION_COMMAND = "dev codex-pilot-authorization"
CODEX_PILOT_AUTHORIZATION_DECISION_STATE = "human_authorized_for_one_run"
CODEX_PILOT_AUTHORIZATION_AUTHOR_ROLE = "human_operator"
CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS = {
    "schema_version",
    "authorization_id",
    "repository",
    "pilot_kind",
    "decision_state",
    "authorizer_role",
    "base_commit_sha",
    "handoff_path",
    "evidence_path",
    "handoff_id",
    "objective",
    "allowed_paths",
    "expected_pr_title",
    "branch_name",
    "validation_commands",
    "budget_metric",
    "budget_ceiling",
    "budget_enforcement_ref",
    "timeout_seconds",
    "cancellation_ref",
    "authentication_runner_ref",
    "branch_permission_ref",
    "pr_permission_ref",
    "duplicate_pr_check_ref",
    "branch_collision_check_ref",
    "codex_no_approve_merge_ref",
    "final_ci_required",
    "assistant_review_required",
    "worker_may_approve",
    "worker_may_merge",
    "one_invocation_only",
    "retry_authorized",
    "background_execution_authorized",
}
CODEX_PILOT_AUTHORIZATION_REFERENCE_FIELDS = [
    "authorization_id",
    "handoff_id",
    "budget_enforcement_ref",
    "cancellation_ref",
    "authentication_runner_ref",
    "branch_permission_ref",
    "pr_permission_ref",
    "duplicate_pr_check_ref",
    "branch_collision_check_ref",
    "codex_no_approve_merge_ref",
]
CODEX_PILOT_AUTHORIZATION_REQUIRED_TRUE_FIELDS = [
    "final_ci_required",
    "assistant_review_required",
    "one_invocation_only",
]
CODEX_PILOT_AUTHORIZATION_REQUIRED_FALSE_FIELDS = [
    "worker_may_approve",
    "worker_may_merge",
    "retry_authorized",
    "background_execution_authorized",
]
CODEX_PILOT_AUTHORIZATION_SAFE_OUTPUT_FIELDS = [
    "authorization_id",
    "repository",
    "pilot_kind",
    "decision_state",
    "authorizer_role",
    "base_commit_sha",
    "handoff_id",
    "objective",
    "allowed_paths",
    "expected_pr_title",
    "branch_name",
    "budget_metric",
    "budget_ceiling",
    "timeout_seconds",
]


def _run_codex_pilot_preflight(
    *,
    handoff_path: Path,
    evidence_path: Path,
) -> dict[str, Any]:
    handoff_filename = _safe_codex_pilot_evidence_input_filename(handoff_path)
    evidence_filename = _safe_codex_pilot_evidence_input_filename(evidence_path)
    handoff_package, handoff_report = _load_codex_invocation_preflight(
        handoff_path
    )
    runtime_report = _run_codex_runtime_probe()
    evidence_report = _inspect_codex_pilot_evidence_package(evidence_path)

    handoff_id = handoff_report.get("handoff_id")
    evidence_handoff_id = evidence_report.get("handoff_id")
    repository = (
        CODEX_PILOT_EVIDENCE_REPOSITORY
        if handoff_report.get("repository") == CODEX_PILOT_EVIDENCE_REPOSITORY
        and evidence_report.get("repository") == CODEX_PILOT_EVIDENCE_REPOSITORY
        else None
    )

    handoff_blockers = _codex_pilot_preflight_handoff_blockers(
        handoff_package=handoff_package,
        handoff_report=handoff_report,
        handoff_filename=handoff_filename,
    )
    runtime_blockers = sorted(runtime_report.get("blockers", []))
    evidence_blockers = sorted(evidence_report.get("blockers", []))
    if evidence_filename is None:
        evidence_blockers = sorted(
            {*evidence_blockers, "evidence input filename is unsafe"}
        )
    binding_blockers = _codex_pilot_preflight_binding_blockers(
        handoff_report=handoff_report,
        evidence_report=evidence_report,
    )

    handoff_static_preflight_passed = bool(handoff_report.get("static_eligible"))
    runtime_local_cli_ready = bool(runtime_report.get("local_cli_ready"))
    evidence_structural_valid = bool(evidence_report.get("structural_valid"))
    evidence_package_complete = bool(
        evidence_report.get("evidence_package_complete")
    )
    binding_passed = not binding_blockers
    eligible_for_authorization_review = all(
        [
            handoff_filename is not None,
            evidence_filename is not None,
            handoff_static_preflight_passed,
            runtime_local_cli_ready,
            evidence_structural_valid,
            evidence_package_complete,
            binding_passed,
        ]
    )

    return {
        "binding_blockers": binding_blockers,
        "binding_passed": binding_passed,
        "blockers_by_source": {
            "binding": binding_blockers,
            "evidence": evidence_blockers,
            "handoff": handoff_blockers,
            "runtime": runtime_blockers,
        },
        "branch_created": False,
        "command": CODEX_PILOT_PREFLIGHT_COMMAND,
        "eligible_for_authorization_review": eligible_for_authorization_review,
        "evidence_complete": evidence_package_complete,
        "evidence_filename": evidence_filename,
        "evidence_structural_valid": evidence_structural_valid,
        "github_access_performed": False,
        "handoff_filename": handoff_filename,
        "handoff_id": handoff_id if handoff_id == evidence_handoff_id else None,
        "handoff_static_preflight_passed": handoff_static_preflight_passed,
        "invocation_authorized": False,
        "invocation_performed": False,
        "mutation_performed": False,
        "network_access_performed": False,
        "pilot_kind": evidence_report.get("pilot_kind"),
        "pilot_ready": False,
        "pull_request_created": False,
        "repository": repository,
        "runtime_local_cli_ready": runtime_local_cli_ready,
        "schema_version": CODEX_PILOT_PREFLIGHT_SCHEMA_VERSION,
    }


def _codex_pilot_preflight_binding_blockers(
    *,
    handoff_report: dict[str, Any],
    evidence_report: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if handoff_report.get("repository") != CODEX_PILOT_EVIDENCE_REPOSITORY:
        blockers.append("handoff repository is invalid")
    if evidence_report.get("repository") != CODEX_PILOT_EVIDENCE_REPOSITORY:
        blockers.append("evidence repository is invalid")
    if evidence_report.get("pilot_kind") != CODEX_PILOT_EVIDENCE_KIND:
        blockers.append("evidence pilot_kind is invalid")

    handoff_id = handoff_report.get("handoff_id")
    evidence_handoff_id = evidence_report.get("handoff_id")
    if not handoff_id or not evidence_handoff_id:
        blockers.append("handoff id binding is unavailable")
    elif handoff_id != evidence_handoff_id:
        blockers.append("handoff id does not match evidence package")
    return sorted(blockers)


def _codex_pilot_preflight_handoff_blockers(
    *,
    handoff_package: dict[str, Any] | None,
    handoff_report: dict[str, Any],
    handoff_filename: str | None,
) -> list[str]:
    blockers: set[str] = set()
    if handoff_filename is None:
        blockers.add("handoff input filename is unsafe")

    raw_blockers = handoff_report.get("package_blockers", [])
    if not raw_blockers:
        return sorted(blockers)

    if handoff_package is None:
        if any("does not exist" in blocker for blocker in raw_blockers):
            blockers.add("handoff package is missing")
        elif any("Invalid JSON" in blocker for blocker in raw_blockers):
            blockers.add("handoff package is malformed")
        else:
            blockers.add("handoff package is unreadable")
    else:
        blockers.add("handoff package failed static preflight")
    return sorted(blockers)


def _print_codex_pilot_preflight_report(report: dict[str, Any]) -> None:
    print("Codex pilot readiness preflight")
    print(f"Schema version: {report['schema_version']}")
    print(f"Command: {report['command']}")
    print(f"Handoff filename: {report['handoff_filename']}")
    print(f"Evidence filename: {report['evidence_filename']}")
    print(f"Repository: {report['repository']}")
    print(f"Handoff ID: {report['handoff_id']}")
    print(f"Pilot kind: {report['pilot_kind']}")
    print(
        "Handoff static preflight passed: "
        f"{_format_yes_no(report['handoff_static_preflight_passed'])}"
    )
    print(
        "Runtime local CLI ready: "
        f"{_format_yes_no(report['runtime_local_cli_ready'])}"
    )
    print(
        "Evidence structural valid: "
        f"{_format_yes_no(report['evidence_structural_valid'])}"
    )
    print(f"Evidence complete: {_format_yes_no(report['evidence_complete'])}")
    print(f"Binding passed: {_format_yes_no(report['binding_passed'])}")
    print(
        "Eligible for authorization review: "
        f"{_format_yes_no(report['eligible_for_authorization_review'])}"
    )
    print("Pilot ready: no")
    print("Invocation authorized: no")
    print("Invocation performed: no")
    print("GitHub access performed: no")
    print("Network access performed: no")
    print("Mutation performed: no")
    print("Branch created: no")
    print("Pull request created: no")
    blockers_by_source = report["blockers_by_source"]
    for source in ["handoff", "runtime", "evidence", "binding"]:
        _print_list(f"{source.title()} blockers", blockers_by_source[source])


def _run_codex_pilot_authorization(
    *,
    handoff_path: Path,
    evidence_path: Path,
    authorization_path: Path,
) -> dict[str, Any]:
    preflight_report = _run_codex_pilot_preflight(
        handoff_path=handoff_path,
        evidence_path=evidence_path,
    )
    authorization_filename = _safe_codex_pilot_evidence_input_filename(
        authorization_path
    )
    package, structural_errors = _load_codex_pilot_authorization_packet(
        authorization_path=authorization_path,
        authorization_filename=authorization_filename,
    )
    if package is not None:
        structural_errors.extend(
            _validate_codex_pilot_authorization_packet(package)
        )

    structural_valid = not structural_errors
    binding_blockers = _codex_pilot_authorization_binding_blockers(
        package=package,
        structural_valid=structural_valid,
        preflight_report=preflight_report,
        handoff_path=handoff_path,
        evidence_path=evidence_path,
    )
    composite_blockers = _codex_pilot_authorization_composite_blockers(
        preflight_report
    )
    composite_preflight_passed = bool(
        preflight_report.get("eligible_for_authorization_review")
    )
    authorization_binding_passed = (
        structural_valid
        and package is not None
        and not binding_blockers
    )
    authorization_packet_valid_for_one_attempt = (
        composite_preflight_passed
        and structural_valid
        and authorization_binding_passed
    )
    safe_fields = _safe_codex_pilot_authorization_fields(
        package=package,
        structural_valid=structural_valid,
    )
    return {
        **safe_fields,
        "authorization_binding_blockers": sorted(binding_blockers),
        "authorization_binding_passed": authorization_binding_passed,
        "authorization_filename": authorization_filename,
        "authorization_packet_valid_for_one_attempt": (
            authorization_packet_valid_for_one_attempt
        ),
        "authorization_structural_errors": sorted(structural_errors),
        "authorization_structural_valid": structural_valid,
        "blockers_by_source": {
            "authorization_binding": sorted(binding_blockers),
            "authorization_structural": sorted(structural_errors),
            "composite_preflight": composite_blockers,
        },
        "branch_created": False,
        "command": CODEX_PILOT_AUTHORIZATION_COMMAND,
        "composite_preflight_passed": composite_preflight_passed,
        "github_access_performed": False,
        "handoff_filename": preflight_report.get("handoff_filename"),
        "evidence_filename": preflight_report.get("evidence_filename"),
        "invocation_performed": False,
        "mutation_performed": False,
        "network_access_performed": False,
        "pilot_ready": False,
        "prompt_submitted": False,
        "pull_request_created": False,
        "schema_version": CODEX_PILOT_AUTHORIZATION_SCHEMA_VERSION,
    }


def _load_codex_pilot_authorization_packet(
    *,
    authorization_path: Path,
    authorization_filename: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if authorization_filename is None:
        errors.append("authorization input filename is unsafe")
    try:
        return _read_json_object_file(authorization_path), errors
    except ValueError as exc:
        error = str(exc)
        if error == "input file is missing":
            errors.append("authorization package is missing")
        elif error == "input file is malformed JSON":
            errors.append("authorization package is malformed")
        elif error == "input JSON root must be an object":
            errors.append("authorization package root must be an object")
        else:
            errors.append("authorization package is unreadable")
        return None, errors


def _validate_codex_pilot_authorization_packet(
    package: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    package_fields = set(package)
    if CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS - package_fields:
        errors.append("authorization package is missing required fields")
    if package_fields - CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS:
        errors.append("authorization package contains unknown fields")

    expected_values = {
        "schema_version": CODEX_PILOT_AUTHORIZATION_SCHEMA_VERSION,
        "repository": CODEX_PILOT_EVIDENCE_REPOSITORY,
        "pilot_kind": CODEX_PILOT_EVIDENCE_KIND,
        "decision_state": CODEX_PILOT_AUTHORIZATION_DECISION_STATE,
        "authorizer_role": CODEX_PILOT_AUTHORIZATION_AUTHOR_ROLE,
        "budget_metric": "tokens",
    }
    for field_name, expected_value in expected_values.items():
        if package.get(field_name) != expected_value:
            errors.append(f"authorization {field_name} is invalid")

    for field_name in CODEX_PILOT_AUTHORIZATION_REFERENCE_FIELDS:
        if not _is_safe_evidence_identifier(package.get(field_name)):
            errors.append(f"authorization {field_name} is invalid")

    if not _is_lower_hex_sha(package.get("base_commit_sha")):
        errors.append("authorization base_commit_sha is invalid")
    for field_name in ["handoff_path", "evidence_path"]:
        if not _is_safe_authorization_json_path(package.get(field_name)):
            errors.append(f"authorization {field_name} is invalid")
    if not _is_safe_authorization_objective(package.get("objective")):
        errors.append("authorization objective is invalid")
    if not _validate_authorization_allowed_paths(package.get("allowed_paths")):
        errors.append("authorization allowed paths are invalid")
    if not _is_safe_authorization_pr_title(package.get("expected_pr_title")):
        errors.append("authorization expected_pr_title is invalid")
    if not _is_safe_authorization_branch_name(package.get("branch_name")):
        errors.append("authorization branch_name is invalid")
    if package.get("validation_commands") != (
        CODEX_INVOCATION_REQUIRED_REPOSITORY_COMMANDS
    ):
        errors.append("authorization validation commands are invalid")

    budget_ceiling = package.get("budget_ceiling")
    if (
        type(budget_ceiling) is not int
        or budget_ceiling < 1
        or budget_ceiling > 1_000_000
    ):
        errors.append("authorization budget is invalid")
    timeout_seconds = package.get("timeout_seconds")
    if (
        type(timeout_seconds) is not int
        or timeout_seconds < 60
        or timeout_seconds > 7200
    ):
        errors.append("authorization timeout is invalid")

    for field_name in CODEX_PILOT_AUTHORIZATION_REQUIRED_TRUE_FIELDS:
        if type(package.get(field_name)) is not bool or package.get(field_name) is not True:
            errors.append(f"authorization {field_name} must be JSON boolean true")
    for field_name in CODEX_PILOT_AUTHORIZATION_REQUIRED_FALSE_FIELDS:
        if type(package.get(field_name)) is not bool or package.get(field_name) is not False:
            errors.append(f"authorization {field_name} must be JSON boolean false")
    return sorted(errors)


def _codex_pilot_authorization_binding_blockers(
    *,
    package: dict[str, Any] | None,
    structural_valid: bool,
    preflight_report: dict[str, Any],
    handoff_path: Path,
    evidence_path: Path,
) -> list[str]:
    if package is None or not structural_valid:
        return []
    blockers: list[str] = []
    if package.get("repository") != preflight_report.get("repository"):
        blockers.append("authorization repository does not match")
    if package.get("pilot_kind") != preflight_report.get("pilot_kind"):
        blockers.append("authorization pilot kind does not match")
    if package.get("handoff_id") != preflight_report.get("handoff_id"):
        blockers.append("authorization handoff id does not match")
    if Path(str(package.get("handoff_path"))).name != handoff_path.name:
        blockers.append("authorization handoff path does not match input")
    if Path(str(package.get("evidence_path"))).name != evidence_path.name:
        blockers.append("authorization evidence path does not match input")

    handoff_package, handoff_report = _load_codex_invocation_preflight(handoff_path)
    if handoff_package is None or not handoff_report.get("static_eligible"):
        return sorted({*blockers, "authorization handoff package is unavailable"})
    task = _as_dict(handoff_package.get("task"))
    declared_paths = _codex_invocation_declared_changed_files(handoff_package)
    if package.get("objective") != task.get("objective"):
        blockers.append("authorization objective does not match handoff")
    if package.get("allowed_paths") != declared_paths:
        blockers.append("authorization allowed paths do not match handoff")
    if package.get("expected_pr_title") != handoff_package.get("expected_pr_title"):
        blockers.append("authorization expected PR title does not match handoff")
    commands = _as_dict(task.get("verification_plan")).get("commands")
    if package.get("validation_commands") != commands:
        blockers.append("authorization validation commands do not match handoff")
    return sorted(blockers)


def _codex_pilot_authorization_composite_blockers(
    preflight_report: dict[str, Any],
) -> list[str]:
    if preflight_report.get("eligible_for_authorization_review"):
        return []
    blockers: list[str] = []
    for source in ["handoff", "runtime", "evidence", "binding"]:
        if preflight_report.get("blockers_by_source", {}).get(source):
            blockers.append(f"composite {source} preflight blocked")
    if not blockers:
        blockers.append("composite preflight is not eligible")
    return sorted(blockers)


def _safe_codex_pilot_authorization_fields(
    *,
    package: dict[str, Any] | None,
    structural_valid: bool,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        field_name: None for field_name in CODEX_PILOT_AUTHORIZATION_SAFE_OUTPUT_FIELDS
    }
    if package is None:
        return fields
    if structural_valid:
        for field_name in CODEX_PILOT_AUTHORIZATION_SAFE_OUTPUT_FIELDS:
            fields[field_name] = package.get(field_name)

    return fields


def _is_lower_hex_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and value == value.strip()
        and all(character in "0123456789abcdef" for character in value)
    )


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_safe_printable_ascii(value: str) -> bool:
    return all(32 <= ord(character) <= 126 for character in value)


def _contains_url_marker(value: str) -> bool:
    lowered = value.lower()
    return "://" in lowered or lowered.startswith("www.")


def _contains_drive_like_path(value: str) -> bool:
    return any(
        character.isalpha()
        and value[index + 1] == ":"
        and value[index + 2] in {"/", "\\"}
        for index, character in enumerate(value[:-2])
    )


def _contains_sensitive_authorization_marker(value: str) -> bool:
    lowered = value.lower()
    markers = [
        "appdata",
        "credential",
        "customer name",
        "password",
        "private customer",
        "private-name",
        "secret",
        "sk-",
        "token",
        "users",
        "/home",
        "home/",
        "~",
    ]
    return any(marker in lowered for marker in markers)


def _has_safe_authorization_text_shape(value: str, max_length: int) -> bool:
    return (
        bool(value)
        and value == value.strip()
        and len(value) <= max_length
        and not _contains_control_character(value)
        and _is_safe_printable_ascii(value)
        and "\t" not in value
        and "\r" not in value
        and "\n" not in value
    )


def _is_conservative_path_segment(segment: str) -> bool:
    return (
        bool(segment)
        and segment not in {".", ".."}
        and all(character.isalnum() or character in "._-" for character in segment)
    )


def _is_safe_repo_relative_path(value: str, *, suffix: str, max_length: int) -> bool:
    if (
        not _has_safe_authorization_text_shape(value, max_length)
        or " " in value
        or "\\" in value
        or ":" in value
        or "//" in value
        or value.startswith("/")
        or value.startswith("~")
        or not value.endswith(suffix)
        or _contains_url_marker(value)
        or _contains_sensitive_authorization_marker(value)
    ):
        return False
    return all(_is_conservative_path_segment(segment) for segment in value.split("/"))


def _is_safe_authorization_json_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and _is_safe_repo_relative_path(value, suffix=".json", max_length=160)
    )


def _is_safe_authorization_objective(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if (
        not _has_safe_authorization_text_shape(value, 200)
        or "/" in value
        or "\\" in value
        or "=" in value
        or _contains_url_marker(value)
        or _contains_drive_like_path(value)
        or _contains_sensitive_authorization_marker(value)
    ):
        return False
    lowered = value.lower()
    return "document" in lowered or "docs" in lowered or "documentation" in lowered


def _validate_authorization_allowed_paths(value: Any) -> bool:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        return False
    if not all(isinstance(path, str) for path in value):
        return False
    if len(set(value)) != len(value) or value != sorted(value):
        return False
    return all(_is_allowed_codex_pilot_authorization_doc_path(path) for path in value)


def _is_safe_authorization_pr_title(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 6 <= len(value) <= 120
        and value.startswith("docs: ")
        and _has_safe_authorization_text_shape(value, 120)
        and "/" not in value
        and "\\" not in value
        and "=" not in value
        and not _contains_url_marker(value)
        and not _contains_drive_like_path(value)
        and not _contains_sensitive_authorization_marker(value)
    )


def _is_safe_authorization_branch_name(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if (
        not _has_safe_authorization_text_shape(value, 100)
        or not value.startswith("codex/")
        or " " in value
        or ".." in value
        or "@{" in value
        or value.endswith("/")
        or value.startswith(".")
        or value.endswith(".")
        or "//" in value
        or _contains_url_marker(value)
        or _contains_drive_like_path(value)
        or _contains_sensitive_authorization_marker(value)
    ):
        return False
    return all(_is_conservative_path_segment(segment) for segment in value.split("/"))

def _print_codex_pilot_authorization_report(report: dict[str, Any]) -> None:
    print("Codex pilot authorization packet inspection")
    print(f"Schema version: {report['schema_version']}")
    print(f"Command: {report['command']}")
    print(f"Handoff filename: {report['handoff_filename']}")
    print(f"Evidence filename: {report['evidence_filename']}")
    print(f"Authorization filename: {report['authorization_filename']}")
    print(f"Authorization ID: {report['authorization_id']}")
    print(f"Repository: {report['repository']}")
    print(f"Pilot kind: {report['pilot_kind']}")
    print(f"Decision state: {report['decision_state']}")
    print(f"Authorizer role: {report['authorizer_role']}")
    print(f"Base commit SHA: {report['base_commit_sha']}")
    print(f"Handoff ID: {report['handoff_id']}")
    print(f"Objective: {report['objective']}")
    _print_list("Allowed paths", report["allowed_paths"] or [])
    print(f"Expected PR title: {report['expected_pr_title']}")
    print(f"Branch name: {report['branch_name']}")
    print(f"Budget metric: {report['budget_metric']}")
    print(f"Budget ceiling: {report['budget_ceiling']}")
    print(f"Timeout seconds: {report['timeout_seconds']}")
    print(
        "Composite preflight passed: "
        f"{_format_yes_no(report['composite_preflight_passed'])}"
    )
    print(
        "Authorization structural valid: "
        f"{_format_yes_no(report['authorization_structural_valid'])}"
    )
    print(
        "Authorization binding passed: "
        f"{_format_yes_no(report['authorization_binding_passed'])}"
    )
    print(
        "Authorization packet valid for one attempt: "
        f"{_format_yes_no(report['authorization_packet_valid_for_one_attempt'])}"
    )
    print("Pilot ready: no")
    print("Invocation performed: no")
    print("Prompt submitted: no")
    print("GitHub access performed: no")
    print("Network access performed: no")
    print("Mutation performed: no")
    print("Branch created: no")
    print("Pull request created: no")
    blockers_by_source = report["blockers_by_source"]
    for source in [
        "composite_preflight",
        "authorization_structural",
        "authorization_binding",
    ]:
        _print_list(f"{source.replace('_', ' ').title()} blockers", blockers_by_source[source])


def _inspect_codex_pilot_evidence_package(path: Path) -> dict[str, Any]:
    structural_errors: list[str] = []
    package: dict[str, Any] | None = None
    input_filename = _safe_codex_pilot_evidence_input_filename(path)
    if input_filename is None:
        structural_errors.append("input filename is unsafe")
    try:
        package = _read_json_object_file(path)
    except ValueError as exc:
        structural_errors.append(str(exc))

    if package is not None:
        structural_errors.extend(_validate_codex_pilot_evidence_package(package))

    control_summary = _codex_pilot_evidence_control_summary(package)
    structural_valid = not structural_errors
    completion_blockers = _codex_pilot_evidence_completion_blockers(
        structural_valid=structural_valid,
        control_summary=control_summary,
    )
    evidence_package_complete = (
        structural_valid
        and not completion_blockers
    )
    return {
        "blocked_controls": control_summary["blocked_controls"],
        "blockers": sorted([*structural_errors, *completion_blockers]),
        "command": CODEX_PILOT_EVIDENCE_COMMAND,
        "completion_blockers": sorted(completion_blockers),
        "evidence_package_complete": evidence_package_complete,
        "github_access_performed": False,
        "handoff_id": _safe_codex_pilot_evidence_value(package, "handoff_id"),
        "input_filename": input_filename,
        "invocation_authorized": False,
        "invocation_performed": False,
        "mutation_performed": False,
        "network_access_performed": False,
        "pilot_kind": _safe_codex_pilot_evidence_value(package, "pilot_kind"),
        "pilot_ready": False,
        "repository": _safe_codex_pilot_evidence_value(package, "repository"),
        "required_control_count": len(CODEX_PILOT_EVIDENCE_CONTROL_IDS),
        "schema_version": CODEX_PILOT_EVIDENCE_SCHEMA_VERSION,
        "structural_errors": sorted(structural_errors),
        "structural_valid": structural_valid,
        "unverified_controls": control_summary["unverified_controls"],
        "verified_control_count": control_summary["verified_control_count"],
    }


def _read_json_object_file(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            value: Any = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError("input file is missing") from exc
    except PermissionError as exc:
        raise ValueError("input file is unreadable") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("input file is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("input file is malformed JSON") from exc
    except OSError as exc:
        raise ValueError("input file is unreadable") from exc

    if not isinstance(value, dict):
        raise ValueError("input JSON root must be an object")
    return value


def _validate_codex_pilot_evidence_package(package: dict[str, Any]) -> list[str]:
    structural_errors: list[str] = []
    package_fields = set(package)
    if package_fields - CODEX_PILOT_EVIDENCE_PACKAGE_FIELDS:
        structural_errors.append("unknown package fields present")
    if CODEX_PILOT_EVIDENCE_PACKAGE_FIELDS - package_fields:
        structural_errors.append("package is missing required fields")

    if package.get("schema_version") != CODEX_PILOT_EVIDENCE_SCHEMA_VERSION:
        structural_errors.append("schema_version is invalid")
    if package.get("repository") != CODEX_PILOT_EVIDENCE_REPOSITORY:
        structural_errors.append("repository is invalid")
    if package.get("pilot_kind") != CODEX_PILOT_EVIDENCE_KIND:
        structural_errors.append("pilot_kind is invalid")

    handoff_id = package.get("handoff_id")
    if not _is_safe_evidence_identifier(handoff_id):
        structural_errors.append("handoff_id is invalid")

    for field_name in ["pilot_ready", "invocation_authorized"]:
        value = package.get(field_name)
        if type(value) is not bool or value is not False:
            structural_errors.append(f"{field_name} must be JSON boolean false")

    controls = package.get("controls")
    if not isinstance(controls, list):
        structural_errors.append("controls must be a list")
        return structural_errors

    seen_control_ids: set[str] = set()
    for index, control in enumerate(controls):
        if not isinstance(control, dict):
            structural_errors.append(f"controls[{index}] must be an object")
            continue
        control_fields = set(control)
        if CODEX_PILOT_EVIDENCE_CONTROL_FIELDS - control_fields:
            structural_errors.append(f"controls[{index}] is missing required fields")
        if control_fields - CODEX_PILOT_EVIDENCE_CONTROL_FIELDS:
            structural_errors.append(f"controls[{index}] contains unknown fields")

        control_id = control.get("control_id")
        if not isinstance(control_id, str):
            structural_errors.append(f"controls[{index}].control_id must be a string")
        elif control_id not in CODEX_PILOT_EVIDENCE_CONTROL_IDS:
            structural_errors.append(f"controls[{index}].control_id is unknown")
        elif control_id in seen_control_ids:
            structural_errors.append(f"duplicate control_id: {control_id}")
        else:
            seen_control_ids.add(control_id)

        status = control.get("status")
        if not isinstance(status, str):
            structural_errors.append(f"controls[{index}].status must be a string")
        elif status not in CODEX_PILOT_EVIDENCE_STATUSES:
            structural_errors.append(f"controls[{index}].status is invalid")

        reviewer_role = control.get("reviewer_role")
        if not isinstance(reviewer_role, str):
            structural_errors.append(
                f"controls[{index}].reviewer_role must be a string"
            )
        elif reviewer_role not in CODEX_PILOT_EVIDENCE_REVIEWER_ROLES:
            structural_errors.append(f"controls[{index}].reviewer_role is invalid")
        elif isinstance(control_id, str) and control_id in (
            CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
        ):
            expected_role = CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS[control_id]
            if reviewer_role != expected_role:
                structural_errors.append(
                    f"controls[{index}].reviewer_role does not match required role"
                )

        evidence_ref = control.get("evidence_ref")
        if not isinstance(evidence_ref, str):
            structural_errors.append(
                f"controls[{index}].evidence_ref must be a string"
            )
        elif status == "verified" and not _is_safe_evidence_identifier(evidence_ref):
            structural_errors.append(
                f"controls[{index}].verified evidence_ref is invalid"
            )
        elif (
            isinstance(status, str)
            and status in {"blocked", "unverified"}
            and evidence_ref
        ):
            if not _is_safe_evidence_identifier(evidence_ref):
                structural_errors.append(
                    f"controls[{index}].evidence_ref is invalid"
                )
        elif (
            isinstance(status, str)
            and status not in CODEX_PILOT_EVIDENCE_STATUSES
            and evidence_ref
        ):
            if not _is_safe_evidence_identifier(evidence_ref):
                structural_errors.append(
                    f"controls[{index}].evidence_ref is invalid"
                )

    for control_id in CODEX_PILOT_EVIDENCE_CONTROL_IDS:
        if control_id not in seen_control_ids:
            structural_errors.append(f"missing control_id: {control_id}")

    return structural_errors


def _codex_pilot_evidence_completion_blockers(
    *,
    structural_valid: bool,
    control_summary: dict[str, Any],
) -> list[str]:
    if not structural_valid:
        return []

    completion_blockers: list[str] = []
    for control_id in control_summary["blocked_controls"]:
        completion_blockers.append(f"{control_id} status is blocked")
    for control_id in control_summary["unverified_controls"]:
        completion_blockers.append(f"{control_id} status is unverified")
    if (
        control_summary["verified_control_count"]
        != len(CODEX_PILOT_EVIDENCE_CONTROL_IDS)
    ):
        completion_blockers.append("not all required controls are verified")
    return completion_blockers


def _safe_codex_pilot_evidence_value(
    package: dict[str, Any] | None,
    field_name: str,
) -> str | None:
    if package is None:
        return None
    value = package.get(field_name)
    if field_name == "repository":
        return value if value == CODEX_PILOT_EVIDENCE_REPOSITORY else None
    if field_name == "pilot_kind":
        return value if value == CODEX_PILOT_EVIDENCE_KIND else None
    return value if _is_safe_evidence_identifier(value) else None


def _safe_codex_pilot_evidence_input_filename(path: Path) -> str | None:
    filename = path.name
    if not _is_safe_evidence_identifier(filename):
        return None
    lowered = filename.lower()
    unsafe_fragments = [
        "://",
        "\\",
        "/",
        ":",
        "sk-",
        "token",
        "secret",
        "password",
        "username",
        "users",
        "home",
        "appdata",
    ]
    if any(fragment in lowered for fragment in unsafe_fragments):
        return None
    return filename


def _codex_pilot_evidence_control_summary(
    package: dict[str, Any] | None,
) -> dict[str, Any]:
    blocked_controls: list[str] = []
    unverified_controls: list[str] = []
    verified_control_count = 0
    controls = package.get("controls") if package else None
    if not isinstance(controls, list):
        return {
            "blocked_controls": blocked_controls,
            "required_control_count": len(CODEX_PILOT_EVIDENCE_CONTROL_IDS),
            "unverified_controls": unverified_controls,
            "verified_control_count": verified_control_count,
        }

    for control in controls:
        if not isinstance(control, dict):
            continue
        control_id = control.get("control_id")
        status = control.get("status")
        if control_id not in CODEX_PILOT_EVIDENCE_CONTROL_IDS:
            continue
        if status == "verified":
            verified_control_count += 1
        elif status == "blocked":
            blocked_controls.append(control_id)
        elif status == "unverified":
            unverified_controls.append(control_id)

    return {
        "blocked_controls": sorted(blocked_controls),
        "required_control_count": len(CODEX_PILOT_EVIDENCE_CONTROL_IDS),
        "unverified_controls": sorted(unverified_controls),
        "verified_control_count": verified_control_count,
    }


def _is_safe_evidence_identifier(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not value or value in {".", ".."} or len(value) > 80:
        return False
    lowered = value.lower()
    unsafe_fragments = [
        "://",
        "\\",
        "/",
        ":",
        "=",
        "sk-",
        "token",
        "secret",
        "password",
        "users",
        "home",
        "appdata",
    ]
    if any(fragment in lowered for fragment in unsafe_fragments):
        return False
    return all(character.isalnum() or character in {"-", "_", "."} for character in value)


def _print_codex_pilot_evidence_report(report: dict[str, Any]) -> None:
    print("Codex pilot evidence package inspection")
    print(f"Schema version: {report['schema_version']}")
    print(f"Command: {report['command']}")
    print(f"Input filename: {report['input_filename']}")
    print(f"Repository: {report['repository']}")
    print(f"Pilot kind: {report['pilot_kind']}")
    print(f"Handoff ID: {report['handoff_id']}")
    print(f"Required controls: {report['required_control_count']}")
    print(f"Verified controls: {report['verified_control_count']}")
    print(f"Structural valid: {_format_yes_no(report['structural_valid'])}")
    print(
        "Evidence package complete: "
        f"{_format_yes_no(report['evidence_package_complete'])}"
    )
    print("Pilot ready: no")
    print("Invocation authorized: no")
    print("Invocation performed: no")
    print("GitHub access performed: no")
    print("Network access performed: no")
    print("Mutation performed: no")
    _print_list("Blocked controls", report["blocked_controls"])
    _print_list("Unverified controls", report["unverified_controls"])
    _print_list("Blockers", report["blockers"])


def _run_codex_runtime_probe() -> dict[str, Any]:
    executable_found = shutil.which("codex") is not None
    blockers: list[str] = []
    version_probe = _empty_codex_runtime_probe_status("not_run")
    exec_help_probe = _empty_codex_runtime_probe_status("not_run")
    sanitized_version = None
    help_text = ""

    if not executable_found:
        blockers.append("codex executable not found")
    else:
        version_probe = _run_fixed_codex_probe(CODEX_RUNTIME_VERSION_ARGV)
        exec_help_probe = _run_fixed_codex_probe(CODEX_RUNTIME_EXEC_HELP_ARGV)

        if version_probe["status"] == "success":
            sanitized_version = _sanitize_codex_version_output(
                version_probe["stdout"]
            )
            if sanitized_version is None:
                version_probe["status"] = "malformed_output"
                blockers.append("version output was empty or malformed")
        else:
            blockers.append(f"version probe {version_probe['status']}")

        if exec_help_probe["status"] == "success":
            help_text = _sanitize_probe_text(exec_help_probe["stdout"])
            if not help_text:
                exec_help_probe["status"] = "malformed_output"
                blockers.append("exec-help output was empty or malformed")
        else:
            blockers.append(f"exec-help probe {exec_help_probe['status']}")

    capabilities = _detect_codex_runtime_capabilities(
        version=sanitized_version,
        exec_help=help_text,
    )
    for field_name, description in CODEX_RUNTIME_CAPABILITY_FIELDS.items():
        if not capabilities[field_name]:
            blockers.append(f"missing capability: {description}")

    local_cli_ready = executable_found and not blockers
    return {
        "blockers": blockers,
        "command": "dev codex-runtime-probe",
        "exec_help_probe": {
            "returncode": exec_help_probe["returncode"],
            "status": exec_help_probe["status"],
            "timed_out": exec_help_probe["timed_out"],
        },
        "ephemeral_option_detected": capabilities["ephemeral_option_detected"],
        "executable_found": executable_found,
        "explicit_budget_option_detected": capabilities[
            "explicit_budget_option_detected"
        ],
        "external_checks_required": CODEX_RUNTIME_EXTERNAL_CHECKS_REQUIRED,
        "github_access_performed": False,
        "invocation_performed": False,
        "json_option_detected": capabilities["json_option_detected"],
        "local_cli_ready": local_cli_ready,
        "mutation_performed": False,
        "network_access_performed": False,
        "non_interactive_exec_detected": capabilities[
            "non_interactive_exec_detected"
        ],
        "output_last_message_option_detected": capabilities[
            "output_last_message_option_detected"
        ],
        "pilot_ready": False,
        "prompt_submitted": False,
        "sandbox_option_detected": capabilities["sandbox_option_detected"],
        "sanitized_cli_version": sanitized_version,
        "schema_version": CODEX_RUNTIME_PROBE_SCHEMA_VERSION,
        "stdin_prompt_input_detected": capabilities[
            "stdin_prompt_input_detected"
        ],
        "version_probe": {
            "returncode": version_probe["returncode"],
            "status": version_probe["status"],
            "timed_out": version_probe["timed_out"],
        },
        "working_directory_option_detected": capabilities[
            "working_directory_option_detected"
        ],
    }


def _empty_codex_runtime_probe_status(status: str) -> dict[str, Any]:
    return {
        "returncode": None,
        "status": status,
        "stdout": "",
        "timed_out": False,
    }


def _run_fixed_codex_probe(argv: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            input=None,
            shell=False,
            text=True,
            timeout=CODEX_RUNTIME_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "status": "timeout",
            "stdout": "",
            "timed_out": True,
        }
    except OSError:
        return {
            "returncode": None,
            "status": "launch_error",
            "stdout": "",
            "timed_out": False,
        }

    status = "success" if completed.returncode == 0 else "nonzero_exit"
    return {
        "returncode": completed.returncode,
        "status": status,
        "stdout": _sanitize_probe_text(completed.stdout),
        "timed_out": False,
    }


def _sanitize_codex_version_output(value: str) -> str | None:
    for line in value.splitlines():
        sanitized = _sanitize_probe_line(line)
        if sanitized:
            return sanitized[:80]
    return None


def _sanitize_probe_text(value: str | None) -> str:
    if not value:
        return ""
    return "\n".join(
        line
        for line in (_sanitize_probe_line(line) for line in value.splitlines())
        if line
    )


def _sanitize_probe_line(value: str) -> str:
    sanitized = " ".join(value.strip().split())
    if not sanitized:
        return ""
    if any(marker in sanitized for marker in ["\\", "/", "=", "sk-"]):
        return ""
    return sanitized[:200]


def _detect_codex_runtime_capabilities(
    *,
    version: str | None,
    exec_help: str,
) -> dict[str, bool]:
    del version
    help_lower = exec_help.lower()
    return {
        "ephemeral_option_detected": _contains_long_option(
            exec_help, "--ephemeral"
        ),
        "explicit_budget_option_detected": _detect_budget_option(exec_help),
        "json_option_detected": _contains_long_option(exec_help, "--json"),
        "non_interactive_exec_detected": (
            "codex exec" in help_lower
            or "usage: exec" in help_lower
            or "usage: codex exec" in help_lower
        ),
        "output_last_message_option_detected": (
            _contains_long_option(exec_help, "--output-last-message")
            or _contains_short_option(exec_help, "-o")
        ),
        "sandbox_option_detected": _contains_long_option(exec_help, "--sandbox"),
        "stdin_prompt_input_detected": (
            "stdin" in help_lower
            or "standard input" in help_lower
            or "prompt from -" in help_lower
        ),
        "working_directory_option_detected": (
            _contains_long_option(exec_help, "--cd")
            or _contains_short_option(exec_help, "-C")
        ),
    }


def _detect_budget_option(help_text: str) -> bool:
    option_lines = [
        line.lower()
        for line in help_text.splitlines()
        if line.strip().startswith("-") or " --" in line
    ]
    return any(
        any(ceiling_word in line for ceiling_word in ["budget", "limit", "max", "ceiling"])
        and any(metric_word in line for metric_word in ["token", "cost", "usage"])
        for line in option_lines
    )


def _contains_long_option(help_text: str, option: str) -> bool:
    return any(
        part == option
        for part in help_text.lower().replace(",", " ").split()
    )


def _contains_short_option(help_text: str, option: str) -> bool:
    return any(part == option for part in help_text.replace(",", " ").split())


def _print_codex_runtime_probe(report: dict[str, Any]) -> None:
    print("Codex CLI runtime capability probe")
    print(f"Schema version: {report['schema_version']}")
    print(f"Executable found: {_format_yes_no(report['executable_found'])}")
    print(f"Sanitized CLI version: {report['sanitized_cli_version']}")
    print(f"Version probe status: {report['version_probe']['status']}")
    print(f"Exec-help probe status: {report['exec_help_probe']['status']}")
    print(f"Local CLI ready: {_format_yes_no(report['local_cli_ready'])}")
    print("Pilot ready: no")
    print("Invocation performed: no")
    print("Prompt submitted: no")
    print("Network access performed: no")
    print("GitHub access performed: no")
    print("Mutation performed: no")
    capability_labels = [
        ("Non-interactive exec", "non_interactive_exec_detected"),
        ("Stdin prompt input", "stdin_prompt_input_detected"),
        ("Ephemeral option", "ephemeral_option_detected"),
        ("Sandbox option", "sandbox_option_detected"),
        ("Working-directory option", "working_directory_option_detected"),
        ("JSON option", "json_option_detected"),
        ("Output last message option", "output_last_message_option_detected"),
        ("Explicit budget option", "explicit_budget_option_detected"),
    ]
    for label, field_name in capability_labels:
        print(f"{label}: {_format_yes_no(report[field_name])}")
    _print_list("Blockers", report["blockers"])
    _print_list("External checks still required", report["external_checks_required"])


CODEX_INVOCATION_ALLOWED_REPOSITORY = "Phoenix-AI-Platform/phoenix-office"
CODEX_INVOCATION_REQUIRED_BASE_BRANCH = "main"
CODEX_INVOCATION_MAX_DOC_FILES = 3
CODEX_INVOCATION_ALLOWED_DOC_PREFIXES = (
    "docs/process/",
    "docs/development/",
)
CODEX_INVOCATION_REQUIRED_PR_HEADINGS = [
    "Summary",
    "Scope",
    "Changed files",
    "Out-of-scope confirmation",
    "Validation performed",
    "Risks",
]
CODEX_INVOCATION_REQUIRED_REPOSITORY_COMMANDS = [
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
]
CODEX_INVOCATION_EXTERNAL_CHECKS_REQUIRED = [
    "duplicate PR detection for the source issue and handoff id",
    "branch collision detection before branch creation",
    "repository credentials and write-permission verification",
    "platform budget or usage ceiling enforcement",
    "operator cancellation support",
    "Codex availability",
    "post-PR CI results for the final head SHA",
    "assistant review verdict before merge",
]
CODEX_INVOCATION_REQUIRED_FALSE_PERMISSIONS = [
    "destructive",
    "execute",
    "network",
]


def _validate_codex_invocation_preflight_package(
    package: dict[str, Any],
) -> list[str]:
    issues = _validate_codex_handoff_package(package)

    if package.get("repository") != CODEX_INVOCATION_ALLOWED_REPOSITORY:
        issues.append(
            "repository must be "
            f"{CODEX_INVOCATION_ALLOWED_REPOSITORY!r}; "
            f"got {package.get('repository')!r}"
        )
    if package.get("base_branch") != CODEX_INVOCATION_REQUIRED_BASE_BRANCH:
        issues.append(
            "base_branch must be "
            f"{CODEX_INVOCATION_REQUIRED_BASE_BRANCH!r}; "
            f"got {package.get('base_branch')!r}"
        )

    task = _as_dict(package.get("task"))
    if task.get("risk_class") != "docs-only":
        issues.append("task.risk_class must be 'docs-only'")

    permissions = task.get("permissions")
    if not isinstance(permissions, dict):
        issues.append("task.permissions must be an object")
    else:
        for field_name in CODEX_INVOCATION_REQUIRED_FALSE_PERMISSIONS:
            value = permissions.get(field_name)
            if type(value) is not bool or value is not False:
                issues.append(
                    f"task.permissions.{field_name} must be JSON boolean "
                    f"False; got {value!r}"
                )

    source = _as_dict(task.get("source"))
    source_uri = source.get("uri")
    if source.get("kind") != "github_issue":
        issues.append("task.source.kind must be 'github_issue'")
    if not _is_phoenix_office_issue_url(source_uri):
        issues.append(
            "task.source.uri must be a Phoenix Office GitHub issue URL"
        )

    allowed_paths = _as_dict(task.get("allowed_resources")).get("paths")
    normalized_allowed_path_set: set[str] = set()
    if not isinstance(allowed_paths, list):
        issues.append("task.allowed_resources.paths must be a list of strings")
    else:
        allowed_string_paths = [
            path for path in allowed_paths if isinstance(path, str)
        ]
        if len(allowed_string_paths) != len(allowed_paths):
            issues.append(
                "task.allowed_resources.paths must contain only strings"
            )
        if not allowed_string_paths:
            issues.append(
                "task.allowed_resources.paths must contain at least 1 path"
            )
        if len(allowed_string_paths) > CODEX_INVOCATION_MAX_DOC_FILES:
            issues.append(
                "task.allowed_resources.paths must contain no more than "
                f"{CODEX_INVOCATION_MAX_DOC_FILES} paths"
            )
        normalized_allowed_paths = [
            path.replace("\\", "/") for path in allowed_string_paths
        ]
        if len(set(normalized_allowed_paths)) != len(normalized_allowed_paths):
            issues.append("task.allowed_resources.paths must be unique")
        for path in normalized_allowed_paths:
            if not _is_allowed_codex_invocation_doc_path(path):
                issues.append(
                    "task.allowed_resources.paths must contain only safe "
                    "repository-relative Markdown files under docs/process/ "
                    "or docs/development/: "
                    f"{path!r}"
                )
        normalized_allowed_path_set = set(normalized_allowed_paths)

    repo_paths = package.get("required_repo_paths")
    if isinstance(repo_paths, list):
        string_paths = [path for path in repo_paths if isinstance(path, str)]
        if not string_paths:
            issues.append("required_repo_paths must contain at least 1 path")
        if len(string_paths) > CODEX_INVOCATION_MAX_DOC_FILES:
            issues.append(
                "required_repo_paths must contain no more than "
                f"{CODEX_INVOCATION_MAX_DOC_FILES} paths"
            )
        for path in string_paths:
            normalized = path.replace("\\", "/")
            if not _is_allowed_codex_invocation_doc_path(normalized):
                issues.append(
                    "required_repo_paths must contain only safe "
                    "repository-relative Markdown files under docs/process/ "
                    "or docs/development/: "
                    f"{path!r}"
                )
            if normalized_allowed_path_set:
                if normalized not in normalized_allowed_path_set:
                    issues.append(
                        "required_repo_paths entries must also appear in "
                        f"task.allowed_resources.paths: {path!r}"
                    )
    else:
        string_paths = []

    headings = package.get("required_pr_body_headings")
    if isinstance(headings, list):
        missing_headings = [
            heading
            for heading in CODEX_INVOCATION_REQUIRED_PR_HEADINGS
            if heading not in headings
        ]
        for heading in missing_headings:
            issues.append(
                f"required_pr_body_headings must include {heading!r}"
            )

    verification_plan = _as_dict(task.get("verification_plan"))
    commands = verification_plan.get("commands")
    if not isinstance(commands, list) or not all(
        isinstance(command, str) for command in commands
    ):
        issues.append("task.verification_plan.commands must be a list of strings")
    else:
        for command in CODEX_INVOCATION_REQUIRED_REPOSITORY_COMMANDS:
            if command not in commands:
                issues.append(
                    "task.verification_plan.commands must include "
                    f"{command!r}"
                )

    return issues


def _build_codex_invocation_preflight_report(
    *,
    package: dict[str, Any] | None,
    path: Path,
    package_blockers: list[str],
) -> dict[str, Any]:
    task = _as_dict(package.get("task")) if package is not None else {}
    source = _as_dict(task.get("source"))
    source_issue_number = (
        _parse_phoenix_office_issue_number(source.get("uri"))
        if source.get("kind") == "github_issue"
        else None
    )
    return {
        "base_branch": package.get("base_branch") if package is not None else None,
        "command": "dev codex-invocation-preflight",
        "declared_changed_files": _codex_invocation_declared_changed_files(
            package
        ),
        "external_checks_required": CODEX_INVOCATION_EXTERNAL_CHECKS_REQUIRED,
        "handoff_id": package.get("handoff_id") if package is not None else None,
        "invocation_authorized": False,
        "message": (
            "Static success never authorizes Codex invocation."
            if not package_blockers
            else "Static preflight found package blockers."
        ),
        "package_blockers": package_blockers,
        "path": str(path),
        "repository": package.get("repository") if package is not None else None,
        "source_issue_number": source_issue_number,
        "static_eligible": not package_blockers,
        "static_success_authorizes_invocation": False,
    }


def _codex_invocation_declared_changed_files(
    package: dict[str, Any] | None,
) -> list[str]:
    if package is None:
        return []
    task = _as_dict(package.get("task"))
    allowed_paths = _as_dict(task.get("allowed_resources")).get("paths")
    if not isinstance(allowed_paths, list):
        return []
    return [
        path.replace("\\", "/")
        for path in allowed_paths
        if isinstance(path, str)
    ]


def _build_codex_invocation_request_failure_report(
    *,
    path: Path,
    preflight_report: dict[str, Any],
) -> dict[str, Any]:
    safe_blockers = [
        blocker.replace(str(path), path.name)
        for blocker in preflight_report["package_blockers"]
    ]
    return {
        "command": "dev codex-invocation-request",
        "error_code": "static_preflight_failed",
        "external_checks_required": preflight_report["external_checks_required"],
        "input_filename": path.name,
        "invocation_authorized": False,
        "message": "Codex invocation request draft was not produced.",
        "package_blockers": safe_blockers,
        "review_required": True,
        "send_performed": False,
        "static_eligible": False,
        "static_success_authorizes_invocation": False,
        "status": "blocked",
        "worker_may_merge": False,
    }


def _build_codex_invocation_request_draft(
    *,
    package: dict[str, Any],
    preflight_report: dict[str, Any],
) -> dict[str, Any]:
    task = _as_dict(package["task"])
    request_identity = f"codex-invocation-request:{package['handoff_id']}"
    rendered_prompt = _render_codex_invocation_request_prompt(
        package=package,
        preflight_report=preflight_report,
    )
    return {
        "base_branch": preflight_report["base_branch"],
        "declared_changed_files": preflight_report["declared_changed_files"],
        "expected_pr_title": package["expected_pr_title"],
        "external_checks_required": preflight_report["external_checks_required"],
        "handoff_id": package["handoff_id"],
        "invocation_authorized": False,
        "original_reviewed_package_prompt": package["prompt"],
        "rendered_prompt": rendered_prompt,
        "repository": preflight_report["repository"],
        "request_id": request_identity,
        "required_pr_body_headings": package["required_pr_body_headings"],
        "required_repository_validation_commands": (
            CODEX_INVOCATION_REQUIRED_REPOSITORY_COMMANDS
        ),
        "review_required": True,
        "schema_version": "codex-invocation-request-draft.v1",
        "send_performed": False,
        "source_issue_number": preflight_report["source_issue_number"],
        "status": "draft",
        "task_id": task["task_id"],
        "task_title": task["title"],
        "worker_may_merge": False,
    }


def _render_codex_invocation_request_prompt(
    *,
    package: dict[str, Any],
    preflight_report: dict[str, Any],
) -> str:
    task = _as_dict(package["task"])
    return "\n".join(
        [
            "# Supervised Codex Invocation Request Draft",
            "",
            "## 1. Supervised Pilot Identity",
            "This is a provider-neutral supervised invocation request draft.",
            "The request is unsent and does not authorize Codex invocation.",
            "",
            "## 2. Source Issue And Handoff",
            f"Source issue number: {preflight_report['source_issue_number']}",
            f"Handoff ID: {package['handoff_id']}",
            f"Task ID: {task['task_id']}",
            f"Task title: {task['title']}",
            "",
            "## 3. Repository And Base Branch",
            f"Repository: {preflight_report['repository']}",
            f"Base branch: {preflight_report['base_branch']}",
            "",
            "## 4. Expected PR Title",
            package["expected_pr_title"],
            "",
            "## 5. Allowed Changed Files",
            *_format_prompt_bullets(preflight_report["declared_changed_files"]),
            "",
            "## 6. Original Reviewed Package Prompt",
            package["prompt"],
            "",
            "## 7. Required Validation Commands",
            *_format_prompt_bullets(CODEX_INVOCATION_REQUIRED_REPOSITORY_COMMANDS),
            "",
            "## 8. Required PR Body Headings",
            *_format_prompt_bullets(package["required_pr_body_headings"]),
            "",
            "## 9. Mandatory Execution Boundaries",
            "- one issue, one branch, one PR",
            "- modify only the declared documentation files",
            "- do not broaden scope",
            "- do not use private customer data",
            "- run and report every required validation",
            "- open one PR and stop",
            "- never approve or merge",
            (
                "- do not comment, label, dispatch workflows, automatically "
                "retry, schedule, queue, or continue in the background"
            ),
            (
                "- stop without mutation when any scope or identity binding "
                "is ambiguous"
            ),
            "",
            "## 10. External Checks Not Claimed",
            *_format_prompt_bullets(preflight_report["external_checks_required"]),
        ]
    )


def _format_prompt_bullets(values: list[Any]) -> list[str]:
    return [f"- {value}" for value in values]


def _print_codex_invocation_request_failure(report: dict[str, Any]) -> None:
    print("Codex invocation request draft: blocked")
    print(f"Input filename: {report['input_filename']}")
    print("Static eligibility: no")
    print("Send performed: no")
    print("Invocation authorized: no")
    print("Worker may merge: no")
    print("Review required: yes")
    print("Rendered prompt: not produced")
    print("Package blockers:")
    for blocker in report["package_blockers"]:
        print(f"  - {blocker}")
    print("External checks still required:")
    for check in report["external_checks_required"]:
        print(f"  - {check}")


def _print_codex_invocation_request_draft(request: dict[str, Any]) -> None:
    print("Codex invocation request draft")
    print(f"Schema version: {request['schema_version']}")
    print(f"Status: {request['status']}")
    print(f"Handoff ID: {request['handoff_id']}")
    print(f"Task ID: {request['task_id']}")
    print(f"Task title: {request['task_title']}")
    print(f"Source issue number: {request['source_issue_number']}")
    print(f"Repository: {request['repository']}")
    print(f"Base branch: {request['base_branch']}")
    print(f"Expected PR title: {request['expected_pr_title']}")
    print("Send performed: no")
    print("Invocation authorized: no")
    print("Worker may merge: no")
    print("Review required: yes")
    _print_list("Declared changed files", request["declared_changed_files"])
    _print_list(
        "External checks still required",
        request["external_checks_required"],
    )
    print("Rendered prompt:")
    print(request["rendered_prompt"])


def _print_codex_invocation_preflight_report(report: dict[str, Any]) -> None:
    print("Codex invocation static preflight")
    print(f"Path: {report['path']}")
    print(f"Handoff ID: {report['handoff_id']}")
    print(f"Source issue number: {report['source_issue_number']}")
    print(f"Repository: {report['repository']}")
    print(f"Base branch: {report['base_branch']}")
    print(f"Static eligibility: {_format_yes_no(report['static_eligible'])}")
    print("Static success authorizes invocation: no")
    print("Codex invocation: not authorized")
    print("GitHub access: not performed")
    print("Mutation: not performed")
    _print_list("Declared changed files", report["declared_changed_files"])
    print("Package blockers:")
    package_blockers = report["package_blockers"]
    if package_blockers:
        for blocker in package_blockers:
            print(f"  - {blocker}")
    else:
        print("  - (none)")
    print("External checks still required:")
    for check in report["external_checks_required"]:
        print(f"  - {check}")


def _is_allowed_codex_invocation_doc_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    if not _is_safe_repo_relative_path(path, suffix=".md", max_length=200):
        return False
    if not path.startswith(CODEX_INVOCATION_ALLOWED_DOC_PREFIXES):
        return False
    lowered_segments = {segment.lower() for segment in path.split("/")}
    forbidden_segments = {
        "api",
        "customer",
        "customers",
        "docx",
        "example",
        "examples",
        "fixture",
        "fixtures",
        "mcp",
        "orchestration",
        "proposal",
        "proposals",
        "server",
        "src",
        "template",
        "templates",
        "test",
        "tests",
        "workflow",
        "workflows",
        "worker",
        "workers",
    }
    return lowered_segments.isdisjoint(forbidden_segments)


def _is_allowed_codex_pilot_authorization_doc_path(path: str) -> bool:
    return (
        _is_allowed_codex_invocation_doc_path(path)
        and path != "docs/development/project_state.md"
    )


def _is_phoenix_office_issue_url(value: Any) -> bool:
    return _parse_phoenix_office_issue_number(value) is not None


def _parse_phoenix_office_issue_number(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    prefix = "https://github.com/Phoenix-AI-Platform/phoenix-office/issues/"
    if not value.startswith(prefix):
        return None
    issue_number = value.removeprefix(prefix)
    if issue_number.isdecimal() and int(issue_number) > 0:
        return int(issue_number)
    return None


def _validate_codex_handoff_package(package: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_values: dict[str, Any] = {
        "schema_version": "codex-handoff-package.v1",
        "worker_type": "codex",
        "invocation_mode": "manual",
    }
    for field_name, expected_value in expected_values.items():
        if package.get(field_name) != expected_value:
            issues.append(
                f"{field_name} must be {expected_value!r}; "
                f"got {package.get(field_name)!r}"
            )

    expected_booleans = {
        "invocation_authorized": False,
        "review_required": True,
        "worker_may_merge": False,
    }
    for field_name, expected_value in expected_booleans.items():
        value = package.get(field_name)
        if type(value) is not bool or value is not expected_value:
            issues.append(
                f"{field_name} must be JSON boolean {expected_value!r}; "
                f"got {value!r}"
            )

    for field_name in [
        "handoff_id",
        "repository",
        "base_branch",
        "expected_pr_title",
        "prompt",
    ]:
        if not _is_non_empty_string(package.get(field_name)):
            issues.append(f"{field_name} must be a non-empty string")

    task = package.get("task")
    if not isinstance(task, dict):
        issues.append("task must be an object")
    else:
        for field_name in ["task_id", "title", "objective"]:
            if not _is_non_empty_string(task.get(field_name)):
                issues.append(f"task.{field_name} must be a non-empty string")

    for field_name in ["required_repo_paths", "required_pr_body_headings"]:
        value = package.get(field_name)
        if not isinstance(value, list):
            issues.append(f"{field_name} must be a list of strings")
        elif not all(isinstance(item, str) for item in value):
            issues.append(f"{field_name} must contain only strings")

    return issues


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


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def _print_codex_handoff_summary(package: dict[str, Any]) -> None:
    task = _as_dict(package.get("task"))
    print(f"Codex handoff package: {package['handoff_id']}")
    print(f"Schema version: {package['schema_version']}")
    print(f"Task ID: {task['task_id']}")
    print(f"Task title: {task['title']}")
    print(f"Repository: {package['repository']}")
    print(f"Base branch: {package['base_branch']}")
    print(f"Expected PR title: {package['expected_pr_title']}")
    print(f"Worker type: {package['worker_type']}")
    print(f"Invocation mode: {package['invocation_mode']}")
    print(
        "Invocation authorized: "
        f"{_format_yes_no(package['invocation_authorized'])}"
    )
    print(f"Review required: {_format_yes_no(package['review_required'])}")
    print(f"Worker may merge: {_format_yes_no(package['worker_may_merge'])}")
    _print_list("Required repository paths", _as_list(package["required_repo_paths"]))
    _print_list(
        "Required PR body headings",
        _as_list(package["required_pr_body_headings"]),
    )
    print("Prompt:")
    print(package["prompt"])
    print("Codex invocation: not authorized")
    print("Merge behavior: not authorized")
    print("Inspection: read-only; no files, GitHub state, workflows, or workers changed")


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
