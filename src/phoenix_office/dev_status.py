"""Read-only Phoenix Office development status helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_NAME = "Phoenix Office"
DEFAULT_PROJECT_STATE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "development" / "project_state.md"
)


@dataclass(frozen=True)
class DevelopmentStatus:
    """Deterministic summary of local repository development state."""

    project_name: str
    status_source_path: Path
    project_state_exists: bool
    latest_recorded_pr_entry: str | None


def read_development_status(
    project_state_path: Path = DEFAULT_PROJECT_STATE_PATH,
) -> DevelopmentStatus:
    """Read development status from local repository documentation only."""

    exists = project_state_path.exists() and project_state_path.is_file()
    latest_entry = None
    if exists:
        latest_entry = latest_project_state_pr_entry(
            project_state_path.read_text(encoding="utf-8")
        )
    return DevelopmentStatus(
        project_name=PROJECT_NAME,
        status_source_path=project_state_path,
        project_state_exists=exists,
        latest_recorded_pr_entry=latest_entry,
    )


def latest_project_state_pr_entry(project_state_text: str) -> str | None:
    """Return the last PR entry from the Current Verified Spine block."""

    in_spine_section = False
    in_spine_block = False
    latest_entry = None

    for raw_line in project_state_text.splitlines():
        line = raw_line.strip()
        if line == "## Current Verified Spine":
            in_spine_section = True
            continue
        if in_spine_section and line.startswith("## "):
            break
        if not in_spine_section:
            continue
        if line.startswith("```"):
            in_spine_block = not in_spine_block
            continue
        if in_spine_block and _is_pr_entry(line):
            latest_entry = line

    return latest_entry


def format_development_status(status: DevelopmentStatus) -> str:
    """Format a concise, deterministic status summary."""

    exists = "yes" if status.project_state_exists else "no"
    latest_entry = status.latest_recorded_pr_entry or "(none)"
    return "\n".join(
        [
            f"project name: {status.project_name}",
            f"status source path: {status.status_source_path}",
            f"project-state file exists: {exists}",
            f"latest recorded PR entry: {latest_entry}",
        ]
    )


def _is_pr_entry(line: str) -> bool:
    return len(line) > 1 and line.startswith("#") and line[1].isdigit()
