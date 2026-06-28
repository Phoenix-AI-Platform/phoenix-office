# Orchestration Output Artifact Policy Design Notes

## Purpose

These notes define future expectations for orchestration output/artifact policy before any orchestration execution could ever be considered.

This document does not implement output/artifact behavior. This document does not generate artifacts. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only, while manual proposal output remains available through the existing explicit CLI workflow:

- Manual proposal DOCX generation exists through the current explicit CLI workflow.
- Output artifact conventions exist for manual outputs.
- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, output/artifact enforcement, operator confirmation enforcement, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Output/Artifact Policy Goal

Any future execution design must require an explicit, inspectable output/artifact policy before execution can be proposed.

The policy should make clear:

- what artifact would be generated
- where it would be written
- whether overwrite is allowed
- whether dry-run mode avoids writing files
- whether generated outputs are excluded from commits
- how private/customer data is handled

## Candidate Future Policy Concepts

Possible future concepts include:

- explicit output path
- explicit artifact type, such as proposal DOCX
- overwrite policy
- dry-run/no-write policy
- generated artifact exclusion from git commits
- sanitized fixture policy
- private/customer-data handling policy
- artifact naming expectations
- audit record expectation if audit persistence is later approved
- operator confirmation should display artifact policy before execution
- validation/preflight should block missing or unsafe artifact policy, if validation/preflight is later approved

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- generate DOCX files
- change DOCX renderer behavior
- change proposal generation behavior
- add execution
- add audit persistence
- add validation/preflight enforcement
- add operator confirmation enforcement
- add plan/review binding enforcement
- add review mutation

## Artifact Safety Expectations

- Generated outputs should not be committed unless explicitly intended as sanitized fixtures.
- Private/customer data must not be added to docs, tests, or examples.
- Dry-run behavior must remain non-writing if present.
- Output decisions must be explicit and not inferred from filenames alone.
- Overwrite behavior must be explicit.
- Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- generate DOCX files as a side effect of inspect, validation, or confirmation commands
- infer output paths from customer names without explicit operator input
- overwrite files without explicit policy
- commit generated private/customer artifacts
- hide execution behind output validation
- treat artifact creation as approval
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Readiness, Audit, Binding, Validation, Operator Confirmation, And Output Conventions

The [output artifact conventions](output_artifact_conventions.md) document current manual output hygiene and commit expectations.

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies artifact and output policy as a required gate before future execution can be proposed.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations for recording output/artifact policy if audit persistence is later approved.

The [orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md) describe future binding expectations that must be satisfied before any plan could be acted on.

The [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) describe future read-only validation/preflight expectations that could check output/artifact policy if separately approved.

The [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) describe future confirmation expectations that should display output/artifact policy before any execution could be proposed.

Explicit output/artifact policy is a required gate before future execution can be proposed and must remain separate from inspection, validation, confirmation, and execution unless separately approved. These notes do not authorize execution, output/artifact policy enforcement, operator confirmation enforcement, validation/preflight enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
