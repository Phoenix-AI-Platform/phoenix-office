# Orchestration Private Data/Secrets Design Notes

## Purpose

These notes define future expectations for private/customer data and secrets handling before any orchestration execution could ever be considered.

This document does not implement private-data or secrets handling behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, private-data/secrets enforcement, redaction behavior, secret scanning behavior, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Private-Data/Secrets Goal

Future orchestration design must protect private/customer data and secrets before execution could ever be proposed.

Private customer data must not be added to docs, tests, examples, or generated committed artifacts. Secrets, API keys, and tokens must not be stored in plans, reviews, fixtures, logs, docs, or generated artifacts.

## Candidate Future Controls

Possible future controls include:

- sanitized fixture requirements
- explicit private/customer data handling policy
- explicit secrets handling policy
- non-sensitive summaries for inspection and result reporting
- avoid storing secrets in plan or review data
- avoid storing unnecessary customer data in audit or result output
- output/artifact policy that keeps private generated files out of commits
- validation/preflight checks for unsafe paths or fixture usage if separately approved
- operator confirmation that warns before handling private/customer data if separately approved

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add private-data or secrets handling behavior
- add redaction behavior
- add secret scanning behavior
- add audit persistence
- add validation/preflight enforcement
- add output/artifact policy enforcement
- add operator confirmation enforcement
- add review mutation
- generate DOCX files

## Safety Expectations

- Private customer data must not be added to docs, tests, examples, or generated committed artifacts.
- Secrets, API keys, and tokens must not be stored in plans, reviews, fixtures, logs, docs, or generated artifacts.
- Future audit/result output must avoid unnecessary private/customer data.
- Sanitized fixtures remain preferred.
- Generated private/customer artifacts should stay local unless explicitly approved as sanitized fixtures.
- Pricing, scope, notes, and customer data must not be inferred.

## Forbidden Shortcuts

Future work must not:

- commit private/customer artifacts
- commit secrets, API keys, or tokens
- place secrets in plans, reviews, fixtures, logs, docs, or generated artifacts
- treat redaction or secret scanning as implemented by this document
- expose unnecessary customer data in audit or result summaries
- hide execution behind data validation
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Audit, Output Policy, Result Reporting, Fixtures, And Project Docs

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations and explicitly avoid unnecessary private/customer data if audit persistence is later approved.

The [orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) describe future output/artifact handling expectations for generated files.

The [orchestration execution result design notes](orchestration_execution_result_design_notes.md) describe future result/reporting expectations that should avoid unnecessary private/customer data.

Existing fixture and project-state docs prefer sanitized examples and forbid private customer data in repo.

Private-data/secrets governance is a required future gate and must remain separate from execution, redaction behavior, secret scanning, audit persistence, mutation, and artifact generation unless separately approved. These notes do not authorize execution, private-data/secrets enforcement, redaction behavior, secret scanning behavior, validation/preflight enforcement, output/artifact policy enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
