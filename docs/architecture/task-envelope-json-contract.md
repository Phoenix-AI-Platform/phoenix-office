# TaskEnvelope JSON Contract

## Purpose

`TaskEnvelope` JSON is the reviewable shape future agents use to propose work before touching code, files, services, workflows, or external systems.

A task envelope captures intent, scope, permissions, approval expectations, and verification expectations. It is a contract for review and routing. It is not execution.

## Current Example

The current serialized example is:

```text
examples/tasks/proposal_generation_task.json
```

That example describes requested proposal-generation work and references the existing `office.generate_proposal` capability. It does not generate a DOCX, invoke a worker, call the CLI, or mutate files.

## JSON Object

A `TaskEnvelope` JSON object currently contains these top-level fields:

- `task_id`: stable task identifier string
- `title`: short human-readable task title
- `objective`: concise statement of intended outcome
- `requester`: requester identity object
- `source`: original request source object
- `status`: task lifecycle string
- `priority`: task priority string
- `constraints`: list of scope or safety constraints
- `acceptance_criteria`: list of completion criteria
- `context_refs`: list of input, output, repository, file, issue, or artifact references
- `allowed_resources`: object mapping resource categories to lists of allowed resource references
- `permissions`: permission switch object
- `approval_policy`: approval requirement object
- `verification_plan`: verification expectation object
- `created_at`: ISO-8601 timestamp string
- `updated_at`: ISO-8601 timestamp string

## Nested Objects

`requester` contains:

- `type`: `human`, `system`, `schedule`, or `github`
- `id`: requester identifier string

`source` contains:

- `kind`: `chat`, `github_issue`, `automation`, or `api`
- `uri`: source URI string or null

`permissions` contains boolean switches:

- `read`
- `write`
- `execute`
- `network`
- `destructive`

`approval_policy` contains:

- `required_before`: list of permission/action names requiring approval before use
- `approvers`: list of approver identifiers

`verification_plan` contains:

- `commands`: list of verification commands expected after implementation
- `evidence_required`: list of evidence categories, such as `test_output`, `lint_output`, `artifact`, or `human_confirmation`

## Review Rules

Reviewers and future agents should treat a `TaskEnvelope` as advisory proposed work until a human explicitly approves the next action.

Before any implementation begins, the envelope should make these review points clear:

- what work is requested
- which files, repositories, artifacts, or capabilities are in scope
- which resources are explicitly allowed
- whether write, execute, network, destructive, or external behavior is requested
- what approval is required before risky behavior
- what evidence should prove completion

## Non-Execution Boundary

Creating, reading, validating, or displaying a `TaskEnvelope` must not by itself:

- modify product code
- modify tests
- modify documentation
- mutate repository state
- call GitHub APIs
- trigger workflows
- execute workers
- execute orchestration
- call MCP tools for side effects
- render DOCX files
- generate artifacts
- contact external services
- send messages, emails, labels, comments, or approvals

Any mutation or execution still requires an explicit user request, a narrow scoped PR or approved command, and the relevant human review gate.

## Determinism Expectations

TaskEnvelope JSON should be deterministic enough for fixture tests, local validation, and review tooling.

Stable expectations:

- enum values serialize as lowercase strings
- timestamps serialize as ISO-8601 strings
- list order is meaningful and should be preserved
- omitted optional lists should use empty lists when serialized by the current contract helpers
- resource references should be explicit strings, not inferred hidden state

## Consumer Guidance

Future agents may read TaskEnvelope JSON to understand proposed work and prepare a plan.

Future agents must not treat TaskEnvelope JSON as permission to act. In particular, an envelope with `permissions.write`, `permissions.execute`, or `permissions.network` set to `true` is a disclosure of requested capability, not approval to use it.

Consumers should fail closed when required fields are missing, enum values are unknown, permissions are ambiguous, or allowed resources do not cover the proposed action.

## Stability Note

Field additions or contract changes require focused tests, updated fixtures, and a dedicated reviewed PR. This document should be updated whenever intentional TaskEnvelope JSON contract changes are made.
