# Phoenix Development Workflow

## Roles

- ChatGPT acts as architect/reviewer.
- Codex and Copilot act as implementation workers.

## Pull Request Process

- Keep work in small, scoped pull requests.
- Each PR should include:
  - Summary
  - Scope
  - Verification
  - Risk
  - Reviewer notes
- Every PR should run:
  - `python -m pytest`
  - `ruff check .`

## Current Safe Platform Spine

```text
architecture docs
  -> Python contracts
  -> plugin capability metadata
  -> capability registry
  -> TaskEnvelope factory
  -> JSON examples
  -> examples index
  -> PR template
```

`TaskEnvelope` and `PluginCapability` should remain the stable contract boundary for workflow and review alignment.

## Developer Workflows

- [Records CLI workflow](records_cli.md) documents the current SQLite-backed customer/job record import, list, show, and export commands.
- [Proposal workflow operator checklist](proposal_workflow_operator_checklist.md) is the short checklist for running the current manual A-1 record-backed proposal workflow.
- [Proposal workflow runbook](proposal_workflow_runbook.md) documents the current manual record-backed proposal command chain from records import through DOCX generation.
- [Output artifact conventions](output_artifact_conventions.md) documents where generated local workflow artifacts should go and what should not be committed.

## Scope Guardrail

Runtime/orchestrator/worker execution should not be introduced unless the task explicitly asks for it.
