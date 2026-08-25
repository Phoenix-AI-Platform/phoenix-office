from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.core import CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS
from phoenix_office.dev import (
    CodexPilotPackageBuildError,
    build_codex_pilot_package,
    codex_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILES = {
    "authorization.json",
    "evidence.json",
    "handoff.json",
}


@pytest.fixture(autouse=True)
def _simulate_canonical_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep package tests independent of feature and detached CI checkouts."""

    monkeypatch.setattr(
        codex_package,
        "_current_branch",
        lambda _repository: "main",
    )


def _head() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        shell=False,
        text=True,
    )
    return completed.stdout.strip()


def _valid_spec(**updates: Any) -> dict[str, Any]:
    reviewers = cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
    spec: dict[str, Any] = {
        "acceptance_criteria": [
            "The supervised Codex package is deterministic and preclaim ready.",
            "The package builder opens no execution or publication authority.",
        ],
        "allowed_paths": ["docs/development/progress_dashboard.md"],
        "base_commit_sha": _head(),
        "branch_name": "codex/issue-073-pilot",
        "budget_ceiling": 225000,
        "constraints": [
            "Edit only the authorized Markdown path.",
            "Do not invoke workers or publish Git state.",
        ],
        "control_references": {
            control_id: f"{control_id}-reviewed"
            for control_id in reviewers
        },
        "expected_pr_title": "docs: record supervised package readiness",
        "handoff_id": "codex-handoff-issue-386",
        "issue_number": 386,
        "objective": "Document the deterministic supervised package builder.",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "reviewed_at": "2026-08-24T12:00:00+00:00",
        "schema_version": "codex-pilot-task-spec.v1",
        "task_id": "issue-386-package-builder",
        "timeout_seconds": 1800,
        "title": "Build deterministic supervised run packages",
    }
    spec.update(updates)
    return spec


def _write_spec(tmp_path: Path, **updates: Any) -> Path:
    path = tmp_path / "task-spec.json"
    path.write_text(
        json.dumps(_valid_spec(**updates), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _build(
    tmp_path: Path,
    *,
    output_name: str = "package",
    authorization_id_factory=None,
    **updates: Any,
) -> tuple[dict[str, Any], Path]:
    output = tmp_path / output_name
    result = build_codex_pilot_package(
        task_spec_path=_write_spec(tmp_path, **updates),
        output_dir=output,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=(
            cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
        ),
        inspector=cli._inspect_codex_pilot_package_build,
        authorization_id_factory=authorization_id_factory,
    )
    return result, output


def _read_package(output: Path) -> dict[str, dict[str, Any]]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in output.iterdir()
    }


def test_valid_package_build_round_trips_existing_validators(
    tmp_path: Path,
) -> None:
    result, output = _build(tmp_path)

    assert result["package_build_result"] == "pass"
    assert result["preclaim_ready"] is True
    assert result["structural_validation_passed"] is True
    assert result["authorization_binding_passed"] is True
    assert result["fingerprint_validation_passed"] is True
    assert set(path.name for path in output.iterdir()) == EXPECTED_FILES
    assert len(result["authorization_fingerprint"]) == 64


def test_authorization_incompatible_objective_fails_before_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_077_objective = (
        "Record the first verified successor-driven supervised Codex autonomy "
        "pilot in the Phoenix development progress dashboard."
    )
    monkeypatch.setattr(
        codex_package,
        "_compose_artifacts",
        lambda **_kwargs: pytest.fail("invalid objective reached composition"),
    )

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path, objective=task_077_objective)

    assert exc_info.value.category == "task_spec_malformed"
    assert not (tmp_path / "package").exists()


def test_repeated_builds_are_substantively_deterministic_with_fresh_identity(
    tmp_path: Path,
) -> None:
    ids = iter(("pilot-auth-issue-386-alpha", "pilot-auth-issue-386-beta"))
    first, first_output = _build(
        tmp_path,
        output_name="first",
        authorization_id_factory=lambda _issue: next(ids),
    )
    second, second_output = _build(
        tmp_path,
        output_name="second",
        authorization_id_factory=lambda _issue: next(ids),
    )
    first_package = _read_package(first_output)
    second_package = _read_package(second_output)

    assert first_package["handoff.json"] == second_package["handoff.json"]
    assert first_package["evidence.json"] == second_package["evidence.json"]
    first_auth = first_package["authorization.json"]
    second_auth = second_package["authorization.json"]
    assert first_auth.pop("authorization_id") != second_auth.pop(
        "authorization_id"
    )
    assert first_auth == second_auth
    assert first["authorization_fingerprint"] != second[
        "authorization_fingerprint"
    ]


def test_default_builds_generate_fresh_authorization_ids(tmp_path: Path) -> None:
    first, _output = _build(tmp_path, output_name="first")
    second, _output = _build(tmp_path, output_name="second")

    assert first["authorization_id"] != second["authorization_id"]


def test_authorization_identity_collision_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "package"
    output.mkdir()
    collision_id = "pilot-auth-issue-386-collision"
    (output / "authorization.json").write_text(
        json.dumps({"authorization_id": collision_id}),
        encoding="utf-8",
    )

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(
            tmp_path,
            authorization_id_factory=lambda _issue: collision_id,
        )

    assert exc_info.value.category == "authorization_identity_collision"


def test_stale_base_sha_is_rejected_before_output(tmp_path: Path) -> None:
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path, base_commit_sha="0" * 40)

    assert exc_info.value.category == "stale_base_commit"
    assert not (tmp_path / "package").exists()


def test_feature_branch_package_build_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        codex_package,
        "_current_branch",
        lambda _repository: "codex/issue-073-builder",
    )

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path)

    assert exc_info.value.category == "noncanonical_base_branch"
    assert not (tmp_path / "package").exists()


def test_detached_head_package_build_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        codex_package,
        "_current_branch",
        lambda _repository: "",
    )

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path)

    assert exc_info.value.category == "noncanonical_base_branch"
    assert not (tmp_path / "package").exists()


def test_exact_main_sha_package_build_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        codex_package,
        "_current_branch",
        lambda _repository: "main",
    )

    result, output = _build(tmp_path)

    assert result["preclaim_ready"] is True
    assert output.is_dir()


@pytest.mark.parametrize(
    ("updates", "category"),
    [
        ({"schema_version": "unknown"}, "task_spec_malformed"),
        ({"allowed_paths": ["src/phoenix_office/cli.py"]}, "unauthorized_path"),
        ({"branch_name": "codex/task-073-pilot"}, "unsafe_branch"),
        ({"branch_name": "feature/issue-073-pilot"}, "unsafe_branch"),
    ],
)
def test_malformed_or_unauthorized_task_spec_is_rejected(
    tmp_path: Path,
    updates: dict[str, Any],
    category: str,
) -> None:
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path, **updates)

    assert exc_info.value.category == category


def test_current_safe_branch_contract_accepts_issue_branch(tmp_path: Path) -> None:
    result, output = _build(tmp_path, branch_name="codex/issue-073-pilot")

    assert result["branch_name"] == "codex/issue-073-pilot"
    assert output.is_dir()


def test_output_inside_registered_git_worktree_is_rejected(
    tmp_path: Path,
) -> None:
    spec = _write_spec(tmp_path)
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        build_codex_pilot_package(
            task_spec_path=spec,
            output_dir=REPOSITORY_ROOT / ".task-073-package",
            repository_root=REPOSITORY_ROOT,
            evidence_control_reviewers=(
                cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
            ),
            inspector=cli._inspect_codex_pilot_package_build,
        )

    assert exc_info.value.category == "output_inside_git_worktree"


def test_output_inside_canonical_venv_is_rejected(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path)
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        build_codex_pilot_package(
            task_spec_path=spec,
            output_dir=REPOSITORY_ROOT / ".venv" / "task-073-package",
            repository_root=REPOSITORY_ROOT,
            evidence_control_reviewers=(
                cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
            ),
            inspector=cli._inspect_codex_pilot_package_build,
        )

    assert exc_info.value.category == "output_inside_venv"


def test_output_inside_absent_canonical_venv_is_rejected_before_parent_resolution(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "synthetic-repository"
    repository.mkdir()
    assert not (repository / ".venv").exists()

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        codex_package._qualify_output_dir(
            repository / ".venv" / "package",
            repository.resolve(strict=True),
        )

    assert exc_info.value.category == "output_inside_venv"


def test_database_shaped_output_location_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path, output_name="customer-records.sqlite3")

    assert exc_info.value.category == "customer_job_store_rejected"


def test_symlink_or_reparse_output_ancestry_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.mkdir()
    original = codex_package._is_link_or_reparse
    monkeypatch.setattr(
        codex_package,
        "_is_link_or_reparse",
        lambda path: path == unsafe_parent or original(path),
    )

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path, output_name="unsafe-parent/package")

    assert exc_info.value.category == "output_symlink_rejected"


def test_validation_commands_remain_exact_in_both_generated_contracts(
    tmp_path: Path,
) -> None:
    _result, output = _build(tmp_path)
    package = _read_package(output)

    assert package["authorization.json"]["validation_commands"] == (
        CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS
    )
    assert package["handoff.json"]["task"]["verification_plan"][
        "commands"
    ] == CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS


def test_builder_never_opens_execution_or_publication_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "SupervisedCodexPilotRunner",
        lambda *_args, **_kwargs: pytest.fail("runner was constructed"),
    )
    result, _output = _build(tmp_path)

    assert result["runner_invoked"] is False
    assert result["claim_created"] is False
    assert result["branch_created"] is False
    assert result["commit_created"] is False
    assert result["push_performed"] is False
    assert result["pr_created"] is False


def test_builder_does_not_run_legacy_codex_runtime_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "_run_codex_runtime_probe",
        lambda: pytest.fail("Codex runtime probe was invoked"),
    )

    result, _output = _build(tmp_path)

    assert result["preclaim_ready"] is True


def test_incompatible_existing_output_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "package"
    output.mkdir()
    (output / "unrelated.txt").write_text("existing", encoding="utf-8")

    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        _build(tmp_path)

    assert exc_info.value.category == "output_artifacts_already_exist"


def test_failed_merged_inspection_publishes_no_partial_package(
    tmp_path: Path,
) -> None:
    def reject(_handoff: Path, _evidence: Path, _authorization: Path):
        return codex_package.CodexPilotPackageInspection(
            composite_preflight_passed=False,
            authorization_structural_valid=True,
            authorization_binding_passed=True,
            authorization_fingerprint_valid=True,
            authorization_fingerprint="a" * 64,
        )

    output = tmp_path / "package"
    with pytest.raises(CodexPilotPackageBuildError) as exc_info:
        build_codex_pilot_package(
            task_spec_path=_write_spec(tmp_path),
            output_dir=output,
            repository_root=REPOSITORY_ROOT,
            evidence_control_reviewers=(
                cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
            ),
            inspector=reject,
        )

    assert exc_info.value.category == "generated_package_validation_failed"
    assert not output.exists()


def test_cli_json_result_is_bounded_and_contains_no_absolute_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = _write_spec(tmp_path)
    output = tmp_path / "package"

    exit_code = cli.main(
        [
            "dev",
            "codex-pilot-package-build",
            str(spec),
            "--output-dir",
            str(output),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["handoff_path"] == "handoff.json"
    assert payload["evidence_path"] == "evidence.json"
    assert payload["authorization_path"] == "authorization.json"
    assert str(tmp_path) not in captured.out
    assert str(REPOSITORY_ROOT) not in captured.out
    assert "credential" not in captured.out.lower()


def test_cli_requires_explicit_output_directory(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.build_parser().parse_args(
            ["dev", "codex-pilot-package-build", str(_write_spec(tmp_path))]
        )

    assert exc_info.value.code == 2


def test_canonical_json_round_trip_has_no_bom_and_one_trailing_newline(
    tmp_path: Path,
) -> None:
    _result, output = _build(tmp_path)

    for filename in EXPECTED_FILES:
        content = (output / filename).read_bytes()
        assert not content.startswith(b"\xef\xbb\xbf")
        assert content.endswith(b"\n")
        assert not content.endswith(b"\n\n")
        assert json.loads(content.decode("utf-8"))
