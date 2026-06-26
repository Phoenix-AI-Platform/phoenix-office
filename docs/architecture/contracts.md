# Phoenix Contract Sketches

These are Markdown-only schema sketches. They are examples for architecture discussion, not runtime schemas yet. Field names, types, and required flags may change when Phoenix Core implementation begins.

The goal is to make the platform contracts concrete enough for issues, PRs, workers, and plugins to align around the same shapes.

## TaskEnvelope

A `TaskEnvelope` describes work that Phoenix can route to a worker.

```text
TaskEnvelope
  task_id: string
  title: string
  objective: string
  requester:
    type: human | system | schedule | github
    id: string
  source:
    kind: chat | github_issue | automation | api
    uri: string?
  status: requested | planned | assigned | in_progress | blocked | completed | failed
  priority: low | normal | high | urgent
  constraints:
    - string
  acceptance_criteria:
    - string
  context_refs:
    - memory://...
    - github://...
    - file://...
  allowed_resources:
    repositories:
      - owner/name
    paths:
      - string
    tools:
      - string
    environments:
      - local | worktree | cloud | device
  permissions:
    read: boolean
    write: boolean
    execute: boolean
    network: boolean
    destructive: boolean
  approval_policy:
    required_before:
      - write
      - execute
      - destructive
      - external_communication
    approvers:
      - human_id
  verification_plan:
    commands:
      - string
    evidence_required:
      - test_output
      - artifact
      - human_confirmation
  created_at: timestamp
  updated_at: timestamp
```

## WorkerEvent

A `WorkerEvent` records worker lifecycle and progress.

```text
WorkerEvent
  event_id: string
  task_id: string
  worker_id: string
  worker_type: codex | chatgpt_architect | local_llm | unity_ai | browser | infrastructure | future
  event_type: accepted | progress | approval_requested | blocked | failed | completed | verified
  message: string
  status: string
  severity: debug | info | warning | error
  data:
    key: value
  artifact_refs:
    - uri
  error:
    code: missing_context | permission_denied | tool_unavailable | validation_failed | execution_failed | policy_blocked
    message: string
    retryable: boolean
  created_at: timestamp
```

## PluginCapability

A `PluginCapability` describes a plugin operation Phoenix can reason about and approve.

```text
PluginCapability
  capability_id: string
  plugin_id: string
  name: string
  version: string
  description: string
  category: office | unifi | unity | home_assistant | docker | windows | linux | synology | cloud | github | future
  operation_type: read | simulate | mutate
  risk_level: low | medium | high | critical
  input_schema_ref: string
  output_schema_ref: string
  required_permissions:
    - read
    - write
    - execute
    - network
    - destructive
  required_secrets:
    - secret_ref
  supports_dry_run: boolean
  requires_approval: boolean
  verification_methods:
    - api_readback
    - test_command
    - log_check
    - artifact_inspection
    - human_confirmation
  failure_modes:
    - code: string
      retryable: boolean
      description: string
```

## ApprovalRequest

An `ApprovalRequest` pauses work before risky execution.

```text
ApprovalRequest
  approval_request_id: string
  task_id: string
  requested_by_worker_id: string
  capability_id: string?
  action: string
  target_resources:
    - uri
  reason: string
  risk_level: low | medium | high | critical
  expected_result: string
  preview:
    summary: string
    diff_ref: uri?
    dry_run_ref: uri?
  rollback_plan: string?
  expires_at: timestamp?
  requested_approvers:
    - human_id
  status: pending | approved | denied | expired | cancelled
  created_at: timestamp
```

## ApprovalRecord

An `ApprovalRecord` captures a human or policy approval decision.

```text
ApprovalRecord
  approval_record_id: string
  approval_request_id: string
  task_id: string
  decision: approved | denied
  decided_by:
    type: human | policy
    id: string
  decision_reason: string?
  approved_scope:
    actions:
      - string
    resources:
      - uri
    expires_at: timestamp?
    single_use: boolean
  conditions:
    - string
  created_at: timestamp
```

## VerificationEvidence

`VerificationEvidence` records proof that work succeeded or failed.

```text
VerificationEvidence
  evidence_id: string
  task_id: string
  worker_id: string?
  capability_id: string?
  evidence_type: test_output | lint_output | api_readback | log_excerpt | screenshot | artifact | human_confirmation
  summary: string
  result: passed | failed | inconclusive
  command: string?
  artifact_refs:
    - uri
  observed_state:
    key: value
  created_at: timestamp
  verified_by:
    type: worker | human | system
    id: string
```

## Contract Principles

- Contracts should be stable enough for workers and plugins to integrate independently.
- Contracts should be permission-aware from the start.
- Contracts should preserve links between intent, approval, execution, and verification.
- Runtime schemas should be generated later from implementation needs, not assumed from these sketches alone.
