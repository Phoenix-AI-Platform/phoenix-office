"""Validate that a pull request body includes required template sections."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = (
    "Summary",
    "Scope",
    "Changed files",
    "Out-of-scope confirmation",
    "Validation performed",
    "Risks",
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def normalize_heading(heading: str) -> str:
    """Normalize a Markdown heading for section-name comparison."""
    return re.sub(r"\s+", " ", heading.strip()).casefold()


def find_markdown_headings(body: str) -> set[str]:
    """Return normalized Markdown heading text from a PR body."""
    headings: set[str] = set()
    for line in body.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            headings.add(normalize_heading(match.group(1)))
    return headings


def missing_required_sections(body: str) -> list[str]:
    """Return required PR template sections missing from the PR body."""
    headings = find_markdown_headings(body)
    return [section for section in REQUIRED_SECTIONS if normalize_heading(section) not in headings]


def load_pr_body_from_event(event_path: str | Path) -> str:
    """Load pull_request.body from a GitHub Actions event payload."""
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull_request = event.get("pull_request") or {}
    return pull_request.get("body") or ""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate required Phoenix pull request description sections."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--body", help="Pull request body text to validate.")
    source.add_argument("--body-file", type=Path, help="Path to a file containing PR body text.")
    source.add_argument(
        "--event-path",
        type=Path,
        help="Path to a GitHub Actions event JSON payload. Defaults to GITHUB_EVENT_PATH.",
    )
    return parser.parse_args(argv)


def _load_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file is not None:
        return args.body_file.read_text(encoding="utf-8")
    event_path = args.event_path or os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        return load_pr_body_from_event(event_path)
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or [])
    body = _load_body(args)
    missing = missing_required_sections(body)

    if missing:
        print("PR body is missing required section headings:", file=sys.stderr)
        for section in missing:
            print(f"- {section}", file=sys.stderr)
        return 1

    print("PR body contains required section headings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
