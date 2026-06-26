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
