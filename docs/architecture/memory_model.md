# Memory Model

Phoenix memory is operational memory: facts, events, approvals, decisions, artifacts, and preferences used to coordinate work safely over time.

Memory is not an unbounded transcript. It is structured, permission-aware platform state.

## Memory Classes

```text
Facts       Stable information about systems, repos, users, devices, and environments
Events      Time-ordered task, worker, plugin, approval, and verification records
Decisions   Architecture choices, policy decisions, and accepted tradeoffs
Artifacts   Files, patches, reports, screenshots, logs, links, and generated outputs
Preferences Human operating preferences and recurring constraints
```

## Memory Flow

```text
Worker observes state
        |
        v
Event emitted -> Phoenix Core validates -> Memory store
        |
        v
Future task receives relevant memory slice
```

Phoenix decides what becomes durable. Workers can recommend memory updates, but should not directly rewrite global memory without policy checks.

## Task Memory

Each task should receive a memory slice containing:

- Relevant issue or task context.
- Prior decisions that constrain the task.
- Environment facts needed to act safely.
- Recent related failures or verification records.
- Human preferences relevant to communication and execution.

The memory slice should exclude unrelated secrets, customer data, and environment details.

## Event Memory

Events are append-only records. Important event types:

- task.created
- task.assigned
- worker.started
- worker.progress
- approval.requested
- approval.granted
- approval.denied
- plugin.executed
- verification.passed
- verification.failed
- task.completed

Events make Phoenix auditable and debuggable.

## Decision Memory

Architecture and policy decisions should be durable. Decision records should include:

- Decision title.
- Context.
- Chosen direction.
- Alternatives considered.
- Consequences.
- Review date if temporary.

This prevents repeated rediscovery and keeps ChatGPT architect work connected to Codex implementation work.

## Secrets And Sensitive Data

Secrets are not ordinary memory. Phoenix memory may store secret references, not raw secret values, unless a secure vault explicitly owns that data.

Sensitive data should be tagged by domain and permission scope. Workers should receive the minimum necessary data.

## Retention

Memory should support retention policies:

- Short-lived task scratch data.
- Durable audit records.
- Long-term architecture decisions.
- Rotating logs.
- Customer or environment data with explicit deletion rules.

Retention is part of security, not cleanup trivia.
