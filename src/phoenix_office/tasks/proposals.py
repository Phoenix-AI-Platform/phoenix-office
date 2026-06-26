"""Contract-only TaskEnvelope factories for proposal generation.

These helpers describe proposal-generation work using Phoenix Core contracts.
They do not execute proposal generation, call the CLI, render DOCX files, or
register plugin runtime behavior.
"""

from phoenix_office.core.contracts import (
    ApprovalPolicy,
    EvidenceType,
    Requester,
    RequesterType,
    SourceKind,
    TaskEnvelope,
    TaskPermissions,
    TaskPriority,
    TaskSource,
    TaskStatus,
    VerificationPlan,
)
from phoenix_office.plugins import registry

PROPOSAL_GENERATION_CAPABILITY_ID = "office.generate_proposal"
_PROPOSAL_OBJECTIVE = (
    "Generate a local proposal DOCX from proposal input and a DOCX template."
)


def create_proposal_generation_task_envelope(
    *,
    task_id: str,
    requester_id: str,
    input_ref: str,
    output_ref: str,
    template_ref: str | None = None,
) -> TaskEnvelope:
    """Create a contract-only task envelope for proposal generation.

    The returned ``TaskEnvelope`` references the existing proposal generation
    capability metadata but does not execute that capability or invoke any
    proposal generation pipeline code.
    """
    capability = registry.get_plugin_capability_by_id(
        PROPOSAL_GENERATION_CAPABILITY_ID
    )
    if capability is None:
        msg = (
            "Required plugin capability is not registered: "
            f"{PROPOSAL_GENERATION_CAPABILITY_ID}"
        )
        raise ValueError(msg)

    context_refs = [input_ref, output_ref]
    if template_ref is not None:
        context_refs.append(template_ref)

    return TaskEnvelope(
        task_id=task_id,
        title="Generate proposal",
        objective=_PROPOSAL_OBJECTIVE,
        requester=Requester(type=RequesterType.HUMAN, id=requester_id),
        source=TaskSource(kind=SourceKind.API),
        status=TaskStatus.REQUESTED,
        priority=TaskPriority.NORMAL,
        constraints=[
            "Do not execute proposal generation from this contract factory."
        ],
        acceptance_criteria=[
            f"The output DOCX artifact exists at {output_ref}.",
            "The output DOCX artifact can be inspected.",
        ],
        context_refs=context_refs,
        allowed_resources={
            "capabilities": [capability.capability_id],
            "paths": context_refs,
        },
        permissions=TaskPermissions(
            read=True,
            write=True,
            execute=False,
            network=False,
            destructive=False,
        ),
        approval_policy=ApprovalPolicy(required_before=[], approvers=[]),
        verification_plan=VerificationPlan(
            commands=[],
            evidence_required=[EvidenceType.ARTIFACT],
        ),
    )
