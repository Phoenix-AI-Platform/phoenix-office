# Orchestration Input Provenance Design Notes

## Purpose

These notes define future expectations for orchestration input provenance before any orchestration execution could ever be considered.

This document does not implement input provenance behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, input provenance enforcement, validation/preflight enforcement, output/artifact policy enforcement, operator confirmation enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Input Provenance Goal

Future orchestration must know which explicit input files, records, review files, and proposal details were used before execution could be proposed.

Future provenance must distinguish explicit operator-provided inputs from derived/generated artifacts. It must not infer pricing, scope, notes, approval, customer data, or output policy.

## Candidate Future Provenance Concepts

Possible future concepts include:

- explicit input file references
- explicit record identifiers
- explicit review file references
- explicit proposal details references
- distinction between operator-provided inputs and derived/generated artifacts
- plan identifier or fingerprint if such a future concept is approved
- review identifier or fingerprint if such a future concept is approved
- non-sensitive provenance summaries for inspection
- validation/preflight checks that confirm expected inputs are present if separately approved
- audit record references if audit persistence is later approved

These provenance concepts are design guidance only and are not implemented.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add input provenance behavior
- add validation/preflight enforcement
- add output/artifact policy enforcement
- add operator confirmation enforcement
- add plan/review binding enforcement
- add audit persistence
- add review mutation
- generate DOCX files

## Safety Expectations

- Future provenance must use explicit input references, not guessed state.
- Future provenance must not infer pricing, scope, notes, approval, customer data, or output policy.
- Future provenance should avoid exposing unnecessary private/customer data.
- Derived/generated artifacts must be distinguishable from operator-provided inputs.
- Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- infer provenance from filenames alone
- treat generated artifacts as operator-provided inputs without explicit marking
- infer approval from an approved-looking review JSON
- infer pricing, scope, notes, customer data, or output policy
- hide execution behind provenance inspection
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Validation/Preflight, Audit, Plan/Review Binding, Output Policy, And Operator Confirmation Notes

The [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) describe future read-only checks that could inspect provenance if separately approved.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations if audit persistence is later approved.

The [orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md) describe future binding expectations that may rely on deterministic input identity if separately approved.

The [orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) describe future output/artifact expectations that provenance must not infer.

The [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) describe future confirmation expectations that should display relevant explicit inputs if separately approved.

Input provenance is a required future governance gate and must remain separate from execution, validation enforcement, audit persistence, mutation, and artifact generation unless separately approved. These notes do not authorize execution, input provenance enforcement, validation/preflight enforcement, output/artifact policy enforcement, operator confirmation enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
