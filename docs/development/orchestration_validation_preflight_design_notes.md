# Orchestration Validation/Preflight Design Notes

## Purpose

These notes define future expectations for a read-only orchestration validation/preflight layer.

This document does not implement validation or preflight behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Preflight Goal

Any future preflight should be read-only and should determine whether a plan/review pair is safe to consider for execution.

Future preflight should block unsafe conditions before execution is even proposed. It should not mutate the plan, mutate the review, or generate artifacts.

## Candidate Future Preflight Checks

Possible future checks include:

- input files exist and are readable
- plan structure is valid
- review structure is valid
- review decision is explicit
- plan/review binding can be verified
- reviewed plan fingerprint matches the current plan fingerprint, if such a future concept is approved
- required operator confirmation is present, if such a future concept is approved
- proposal input details are explicit
- pricing, scope, and notes are not inferred
- output/artifact policy is explicit
- private/customer data handling policy is respected
- dry-run mode remains available
- unsupported command shapes remain rejected

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a validator API
- define a CLI command
- define error codes
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add audit persistence
- add review mutation
- generate DOCX files

## Failure/Result Expectations

Future preflight result categories may include:

- pass
- warning
- blocked
- not applicable

These categories are not implemented here.

## Privacy And Determinism Expectations

Preflight should avoid exposing unnecessary customer/private data.

Preflight should evaluate deterministic plan/review content, not inferred state. Proposal pricing, scope, and notes must not be inferred. Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- make preflight mutate plans or reviews
- hide execution behind validation or inspect commands
- generate DOCX files as a validation side effect
- trust filenames alone as proof of binding
- execute from an approved-looking review JSON alone
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Readiness, Audit, And Binding Notes

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies validation/preflight as part of the minimum future PR sequence before execution can be considered.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations for validation-blocked and execution-related outcomes.

The [orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md) describe the future binding expectations that validation/preflight would need to check before execution could be proposed.

Validation/preflight is a required gate before future execution can be proposed and must remain read-only unless separately approved. These notes do not authorize execution, validation/preflight enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
