"""Check that project_state.md records a pull request number."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_PROJECT_STATE_PATH = Path("docs/development/project_state.md")


def has_project_state_entry(project_state_text: str, pr_number: int) -> bool:
    """Return whether project state text contains an entry for the PR number."""
    pattern = re.compile(rf"(?<!\d)#{pr_number}(?!\d)")
    return pattern.search(project_state_text) is not None


def check_project_state_entry(project_state_path: Path, pr_number: int) -> bool:
    """Read project state and check for an entry containing the PR number."""
    project_state_text = project_state_path.read_text(encoding="utf-8")
    return has_project_state_entry(project_state_text, pr_number)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether docs/development/project_state.md records a PR number."
    )
    parser.add_argument(
        "--pr-number", type=int, required=True, help="Pull request number to find."
    )
    parser.add_argument(
        "--project-state-path",
        type=Path,
        default=DEFAULT_PROJECT_STATE_PATH,
        help="Path to project_state.md. Defaults to docs/development/project_state.md.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or [])
    project_state_path = args.project_state_path
    pr_number = args.pr_number

    if not project_state_path.exists():
        print(f"Project state file not found: {project_state_path}", file=sys.stderr)
        return 1

    if check_project_state_entry(project_state_path, pr_number):
        print(f"Project state contains entry for PR #{pr_number}.")
        return 0

    print(
        f"Project state is missing an entry for PR #{pr_number}: {project_state_path}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
