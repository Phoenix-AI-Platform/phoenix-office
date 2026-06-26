"""Tests for proposal-generation TaskEnvelope factories."""

import pytest

from phoenix_office.core.contracts import (
    EvidenceType,
    RequesterType,
    SourceKind,
    TaskEnvelope,
    TaskPriority,
    TaskStatus,
)
from phoenix_office.plugins import registry
from phoenix_office.tasks.proposals import (
    PROPOSAL_GENERATION_CAPABILITY_ID,
    create_proposal_generation_task_envelope,
)


def _create_task(template_ref: str | None = "template://a1") -> TaskEnvelope:
    return create_proposal_generation_task_envelope(
        task_id="task-1",
        requester_id="matth",
        input_ref="proposal://input.json",
        output_ref="proposal://output.docx",
        template_ref=template_ref,
    )


def test_factory_returns_task_envelope():
    task = _create_task()

    assert isinstance(task, TaskEnvelope)


def test_task_envelope_references_proposal_generation_capability():
    task = _create_task()

    assert task.allowed_resources["capabilities"] == [
        PROPOSAL_GENERATION_CAPABILITY_ID
    ]


def test_task_envelope_requester_source_status_and_priority_are_correct():
    task = _create_task()

    assert task.requester.type is RequesterType.HUMAN
    assert task.requester.id == "matth"
    assert task.source.kind is SourceKind.API
    assert task.status is TaskStatus.REQUESTED
    assert task.priority is TaskPriority.NORMAL


def test_task_envelope_permissions_are_read_write_only():
    task = _create_task()

    assert task.permissions.read is True
    assert task.permissions.write is True
    assert task.permissions.execute is False
    assert task.permissions.network is False
    assert task.permissions.destructive is False
    assert task.approval_policy.required_before == []


def test_task_envelope_context_refs_include_input_output_and_template_refs():
    task = _create_task()

    assert task.context_refs == [
        "proposal://input.json",
        "proposal://output.docx",
        "template://a1",
    ]
    assert task.allowed_resources["paths"] == task.context_refs


def test_task_envelope_context_refs_allow_missing_template_ref():
    task = _create_task(template_ref=None)

    assert task.context_refs == ["proposal://input.json", "proposal://output.docx"]
    assert task.allowed_resources["paths"] == task.context_refs


def test_task_envelope_verification_plan_expects_artifact_inspection():
    task = _create_task()

    assert task.verification_plan.evidence_required == [EvidenceType.ARTIFACT]
    assert any(
        "output DOCX artifact exists" in criterion
        for criterion in task.acceptance_criteria
    )
    assert any(
        "can be inspected" in criterion for criterion in task.acceptance_criteria
    )


def test_factory_raises_when_proposal_capability_is_missing(monkeypatch):
    monkeypatch.setattr(registry, "get_plugin_capability_by_id", lambda _: None)

    with pytest.raises(ValueError, match=PROPOSAL_GENERATION_CAPABILITY_ID):
        _create_task()
