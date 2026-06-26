"""Command-line interface for Phoenix Office."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from phoenix_office.models.proposal import ProposalInput
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
    if not template_path.exists():
        print(f"Error: DOCX template file does not exist: {template_path}", file=sys.stderr)
        return 1
    if not template_path.is_file():
        print(f"Error: DOCX template path is not a file: {template_path}", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
