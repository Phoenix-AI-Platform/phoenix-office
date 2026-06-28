# Orchestration Permission/Capability Boundary Design Notes

## Purpose

These notes define future expectations for orchestration permission and capability boundaries before any orchestration execution could ever be considered.

This document does not implement permission or capability enforcement. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Existing capability metadata and `TaskEnvelope` work remains non-executing.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, permission enforcement, capability enforcement, authorization checks, validation/preflight enforcement, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Permission/Capability Goal

Future execution must be limited to explicitly approved capabilities.

Future workflows must not silently cross plugin or capability boundaries. Future capability checks should be explicit and inspectable if separately approved.

## Candidate Future Capability Controls

Possible future controls include:

- explicit capability identifiers in planned work
- capability lookup against registered metadata if separately approved
- explicit permission requirements for a proposed capability
- explicit allowed-resource boundaries
- explicit human approval before risky capability use
- validation/preflight checks that inspect capability boundaries if separately approved
- operator confirmation that displays capability and permission scope if separately approved
- audit references to capability and permission scope if audit persistence is later approved

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change capability metadata contracts
- change `TaskEnvelope` contracts
- add execution
- add authorization
- add permissions
- add runtime capability checks
- add validation/preflight enforcement
- add operator confirmation enforcement
- add audit persistence
- add review mutation
- generate DOCX files

## Safety Expectations

- Future execution must be limited to explicitly approved capabilities.
- Future workflows must not silently cross plugin or capability boundaries.
- Existing capability metadata and `TaskEnvelope` work remains non-executing.
- Future capability checks should be explicit and inspectable if separately approved.
- Pricing, scope, notes, approval, output policy, and capability scope must not be inferred.

## Forbidden Shortcuts

Future work must not:

- execute because capability metadata exists
- treat `TaskEnvelope` data as runtime authorization
- silently cross plugin boundaries
- infer permissions from filenames, titles, or approved-looking JSON
- hide execution behind capability inspection
- add authorization, permissions, or runtime checks as a side effect
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Plugin Registry, TaskEnvelope, Validation/Preflight, Operator Confirmation, And Execution Command Surface Notes

Existing plugin registry and `TaskEnvelope` work define metadata and contract examples only; they do not execute capabilities.

The [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) describe future read-only checks that could inspect capability boundaries if separately approved.

The [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) describe future confirmation expectations that should display capability and permission scope if separately approved.

The [orchestration execution command surface design notes](orchestration_execution_command_surface_design_notes.md) describe future command-surface expectations that must remain explicit and separate from inspection.

Permission/capability boundaries are required future governance gates and must remain separate from execution, authorization enforcement, runtime capability checks, audit persistence, mutation, and artifact generation unless separately approved. These notes do not authorize execution, permission enforcement, capability enforcement, authorization checks, validation/preflight enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
