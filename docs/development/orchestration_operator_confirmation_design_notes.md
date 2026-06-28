# Orchestration Operator Confirmation Design Notes

## Purpose

These notes define future expectations for explicit human/operator confirmation before any orchestration execution could ever be considered.

This document does not implement operator confirmation behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, operator confirmation enforcement, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Confirmation Goal

Any future execution design must require a deliberate operator confirmation step after plan inspection, review inspection, validation/preflight, and plan/review binding checks.

The confirmation should make clear the exact plan, review decision, output/artifact policy, and command or workflow that would be acted on.

## Candidate Confirmation Concepts

Possible future concepts include:

- explicit operator confirmation prompt
- exact plan identifier or fingerprint displayed to the operator
- exact review identifier or fingerprint displayed to the operator
- review decision displayed to the operator
- output/artifact policy displayed to the operator
- dry-run status displayed to the operator
- operator must confirm intent after seeing the above
- audit record should capture whether confirmation was provided, if audit persistence is later approved
- cancellation path must be safe and non-mutating

These are design concepts only. They do not define a schema, API, CLI command, prompt wording, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define prompt wording
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add audit persistence
- add validation/preflight enforcement
- add plan/review binding enforcement
- add review mutation
- generate DOCX files

## Confirmation Safety Expectations

- Confirmation should be explicit, not inferred from the presence of approved-looking JSON.
- Confirmation should happen after read-only validation/preflight, not before.
- Cancellation must not mutate plans or reviews.
- Confirmation must not infer pricing, scope, notes, or output decisions.
- Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- treat approved review JSON as operator confirmation
- treat opening or inspecting a plan as confirmation
- treat filenames or timestamps as confirmation
- hide execution behind validation or inspect commands
- mutate review decisions from confirmation
- generate DOCX files as a confirmation side effect
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Readiness, Audit, Binding, And Validation Notes

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies explicit operator confirmation as a required gate before future execution can be proposed.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations for recording whether confirmation was provided, if audit persistence is later approved.

The [orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md) describe future binding expectations that must be checked before operator confirmation could be meaningful.

The [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) describe future read-only validation/preflight expectations that should run before confirmation.

Operator confirmation is a required gate before future execution can be proposed and must remain separate from inspection, review mutation, validation, and execution unless separately approved. These notes do not authorize execution, operator confirmation enforcement, validation/preflight enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
