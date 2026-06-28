# Orchestration Dry-Run/No-Write Design Notes

## Purpose

These notes define future expectations for orchestration dry-run/no-write behavior before any orchestration execution could ever be considered.

This document does not implement dry-run behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, dry-run enforcement, output/artifact policy enforcement, operator confirmation enforcement, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Dry-Run/No-Write Goal

Future dry-run should describe what would happen without doing it.

A future dry-run/no-write layer should make proposed actions, inputs, review state, and output/artifact policy visible without writing files, mutating records, mutating reviews, generating DOCX files, enqueueing jobs, or persisting audit records unless those behaviors are separately approved.

Future dry-run must not be treated as approval.

## Candidate Future Dry-Run Expectations

Possible future expectations include:

- show the workflow or command that would be considered
- show the plan identifier or fingerprint if such a future concept is approved
- show the review decision and binding status if such future concepts are approved
- show validation/preflight status if such a future concept is approved
- show output/artifact policy without creating artifacts
- show whether execution would be blocked, warned, or eligible for operator consideration
- preserve a no-write mode that does not generate DOCX files
- preserve a no-mutation mode that does not alter records, plans, reviews, or approvals

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- generate DOCX files
- change proposal generation behavior
- add execution
- add dry-run enforcement
- add audit persistence
- add validation/preflight enforcement
- add operator confirmation enforcement
- add output/artifact policy enforcement
- add plan/review binding enforcement
- add review mutation

## Safety Expectations

- Future dry-run should not write files.
- Future dry-run should not mutate reviews, records, plans, approvals, or stored state.
- Future dry-run should not generate DOCX files.
- Future dry-run should not enqueue jobs.
- Future dry-run should not persist audit records unless separately approved.
- Future dry-run should not infer pricing, scope, notes, or output paths.
- Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- treat dry-run as approval
- hide execution behind dry-run commands
- generate DOCX files as a dry-run side effect
- mutate review decisions during dry-run
- mutate records during dry-run
- infer output paths from customer names without explicit operator input
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Readiness, Validation/Preflight, Operator Confirmation, Output Policy, And Audit Notes

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies dry-run preservation as a required gate before future execution can be proposed.

The [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) describe future read-only checks that could inform dry-run output if separately approved.

The [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) describe future confirmation expectations that must remain separate from dry-run.

The [orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) describe future output/artifact policy expectations that dry-run should display without creating artifacts.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations if audit persistence is later approved.

Dry-run/no-write behavior is a required future design gate and must remain non-executing unless separately approved. These notes do not authorize execution, dry-run enforcement, output/artifact policy enforcement, operator confirmation enforcement, validation/preflight enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
