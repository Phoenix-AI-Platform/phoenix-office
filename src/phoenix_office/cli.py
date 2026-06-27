"""Command-line interface for Phoenix Office."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from phoenix_office.models.proposal import ProposalInput
from phoenix_office.plugins.registry import get_registered_plugin_capabilities
from phoenix_office.proposal_intake import collect_proposal_input
from phoenix_office.records import (
    create_sqlite_record_store,
    customer_records_to_json,
    import_customer_record_file,
    import_customer_records_file,
    import_job_record_file,
    import_job_records_file,
    job_records_to_json,
)
from phoenix_office.renderers import DocxProposalRenderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phoenix-office")
    subparsers = parser.add_subparsers(dest="command")

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
    generate_parser.set_defaults(func=generate_proposal)

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

    return parser


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
        result = DocxProposalRenderer().render(proposal, template_path, output_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a useful failure.
        print(f"Error: failed to render proposal DOCX: {exc}", file=sys.stderr)
        return 1

    print(f"Generated proposal DOCX: {result}")
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
                print(f"{job.job_id}\t{job.customer_id}\t{job.job_name}\t{job.status.value}")
        else:
            print("No jobs found.")
        return 0

    print(f"Error: unsupported records list kind: {args.records_list_kind}", file=sys.stderr)
    return 1


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


def _print_list(label: str, values: list[Any]) -> None:
    print(f"{label}:")
    if not values:
        print("  - (none)")
        return
    for value in values:
        print(f"  - {value}")


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
