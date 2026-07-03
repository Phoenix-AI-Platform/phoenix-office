"""Static tests for the manual Codex handoff dry-run workflow."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/codex_handoff_dry_run.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_codex_handoff_dry_run_workflow_exists():
    assert WORKFLOW.exists()


def test_codex_handoff_dry_run_workflow_is_manual_only():
    text = _workflow_text()

    assert "on:\n  workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "schedule:" not in text
    assert "workflow_run:" not in text


def test_codex_handoff_dry_run_handoff_path_input_is_required():
    text = _workflow_text()

    assert "handoff_path:" in text
    assert "required: true" in text
    assert "type: string" in text
    assert "default: examples/tasks/codex_handoff_package.json" in text
    assert "Repository-relative path to a committed Codex handoff package JSON file" in text


def test_codex_handoff_dry_run_permissions_are_read_only():
    text = _workflow_text()

    assert "permissions:\n  contents: read" in text
    assert "contents: write" not in text
    assert "pull-requests: write" not in text
    assert "issues: write" not in text
    assert "actions: write" not in text


def test_codex_handoff_dry_run_uses_supported_setup_actions():
    text = _workflow_text()

    assert "uses: actions/checkout@v4" in text
    assert "uses: actions/setup-python@v5" in text
    assert 'python-version: "3.12"' in text
    assert 'python -m pip install -e ".[dev]"' in text


def test_codex_handoff_dry_run_runs_text_and_json_inspection():
    text = _workflow_text()

    assert 'python -m phoenix_office.cli dev codex-handoff "$RESOLVED_HANDOFF_PATH"' in text
    assert (
        'python -m phoenix_office.cli dev codex-handoff "$RESOLVED_HANDOFF_PATH" '
        "--json \\"
    ) in text
    assert '> "$RUNNER_TEMP/codex-handoff-package.json"' in text


def test_codex_handoff_dry_run_uploads_only_normalized_artifact():
    text = _workflow_text()

    assert "uses: actions/upload-artifact@v4" in text
    assert "name: codex-handoff-dry-run" in text
    assert "path: ${{ runner.temp }}/codex-handoff-package.json" in text
    assert "retention-days: 7" in text
    assert "output/" not in text


def test_codex_handoff_dry_run_path_containment_validation_is_present():
    text = _workflow_text()

    assert 'workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()' in text
    assert "candidate.is_absolute()" in text
    assert "resolved = (workspace / candidate).resolve()" in text
    assert "resolved.relative_to(workspace)" in text
    assert "resolved.exists()" in text
    assert "resolved.is_file()" in text
    assert "RESOLVED_HANDOFF_PATH" in text


def test_codex_handoff_dry_run_summary_states_non_invocation_boundary():
    text = _workflow_text()

    assert "Dry run completed." in text
    assert "The handoff package was validated." in text
    assert "Normalized artifact name: codex-handoff-dry-run." in text
    assert "Codex invocation was not authorized or performed." in text
    assert "PR approval was not authorized or performed." in text
    assert "PR merge was not authorized or performed." in text


def test_codex_handoff_dry_run_excludes_mutating_automation_surfaces():
    text = _workflow_text().casefold()
    forbidden_fragments = [
        "actions/github-script",
        "api.github.com",
        "graphql",
        "issues:",
        "pull-requests:",
        "checks:",
        "statuses:",
        "secrets.",
        "workflow_dispatch:",
        "workflow_run:",
        "createcomment",
        "add-label",
        "remove-label",
        "approve",
        "merge --",
        "gh pr",
        "gh api",
        "openai",
        "codex invoke",
        "codex run",
      ]
    for fragment in forbidden_fragments:
        if fragment == "workflow_dispatch:":
            assert text.count(fragment) == 1
        else:
            assert fragment not in text
