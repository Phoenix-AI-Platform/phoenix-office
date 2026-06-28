# Orchestration Cancellation/Rollback Design Notes

## Purpose

These notes define future expectations for orchestration cancellation, rollback, and recovery concepts before any orchestration execution could ever be considered.

This document does not implement cancellation or rollback behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- Current orchestration cannot execute, so there is nothing to cancel or roll back.
- No execution, cancellation behavior, rollback behavior, result reporting behavior, output/artifact policy enforcement, operator confirmation enforcement, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Cancellation Goal

Future cancellation should be safe and non-mutating when no execution has begun.

If execution is ever separately approved, any cancellation design must clearly distinguish work that has not started, work blocked before execution, work cancelled before artifact generation, and work interrupted after partial side effects.

Cancellation must not mutate review approval state.

## Future Rollback/Recovery Expectations

Future rollback must not be promised unless specific reversible actions are designed and approved.

Future partial-failure handling must be explicit. Artifact cleanup must not delete user files without explicit policy. Recovery behavior must distinguish generated artifacts, records, reviews, audit entries, and external side effects if any are ever separately approved.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add cancellation behavior
- add rollback behavior
- add result reporting behavior
- add audit persistence
- add validation/preflight enforcement
- add operator confirmation enforcement
- add output/artifact policy enforcement
- add plan/review binding enforcement
- add review mutation
- generate DOCX files

## Safety Expectations

- Cancellation must not mutate review approval state.
- Cancellation before execution should be non-mutating.
- Rollback must not be claimed for irreversible actions.
- Partial-failure handling must be explicit before execution is proposed.
- Artifact cleanup must not delete user files without explicit policy.
- Private/customer data must not be added to docs, tests, or examples.
- Pricing, scope, notes, output decisions, and rollback behavior must not be inferred.

## Forbidden Shortcuts

Future work must not:

- promise rollback without designed reversible actions
- delete generated or user files without explicit policy
- mutate review decisions during cancellation
- treat cancellation as rejection or approval mutation
- hide execution behind cancellation or recovery commands
- generate DOCX files as a cancellation or rollback side effect
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Output Policy, Audit, Operator Confirmation, And Result Notes

The [orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) describe future output/artifact expectations that must make cleanup and overwrite policy explicit before execution could be proposed.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations for cancellation, blocked, failed, and partial outcomes if audit persistence is later approved.

The [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) describe future confirmation expectations that must make cancellation and output implications clear before execution could be proposed.

The [orchestration execution result design notes](orchestration_execution_result_design_notes.md) describe future result categories that may distinguish blocked, cancelled, succeeded, and failed outcomes if separately approved.

Cancellation/rollback design is a required future gate and must remain separate from execution, review mutation, output generation, and audit persistence unless separately approved. These notes do not authorize execution, cancellation behavior, rollback behavior, result reporting behavior, output/artifact policy enforcement, operator confirmation enforcement, validation/preflight enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
