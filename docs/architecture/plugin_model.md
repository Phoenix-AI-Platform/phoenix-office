# Plugin Model

Plugins expose domain capabilities to Phoenix through consistent contracts. A plugin may integrate with APIs, files, local tools, devices, repositories, or infrastructure.

Phoenix should be able to reason about a plugin without knowing every implementation detail.

## Plugin Responsibilities

A plugin defines:

- Capabilities: operations the plugin can perform.
- Schemas: inputs, outputs, and validation errors.
- Permissions: required scopes for each operation.
- Secrets: credential references needed by operations.
- Risk levels: read-only, write, destructive, external, financial, or production-impacting.
- Simulation: dry-run support when available.
- Verification: checks that prove the operation succeeded.
- Events: emitted lifecycle and audit events.

## Capability Shape

A capability should be explicit:

```text
capability: unifi.optimize_channel_plan
inputs: site_id, devices, constraints
risk: network_change
supports_simulation: true
requires_approval: true
outputs: proposed_plan, expected_impact, verification_steps
```

Capabilities should be easier to approve than raw scripts.

## Plugin Categories

Near-term plugin categories:

- Office: proposal generation, documents, spreadsheets, customer office workflows.
- UniFi: network observation, optimization recommendations, safe configuration changes.
- Unity: editor workflows, game assets, scene operations, build automation.
- Home Assistant: device state, routines, automations, safe home operations.
- Docker: container lifecycle, compose stacks, logs, health checks.
- Windows: services, scheduled tasks, files, local app automation.
- Linux: services, packages, logs, systemd, shell workflows.
- Synology: storage, backups, containers, package operations.
- Cloud: deployments, infrastructure, monitoring, cost and security operations.
- GitHub: issues, branches, PRs, reviews, CI, releases.

## Plugin Runtime Boundary

Plugins do not own orchestration policy. They expose capability metadata and execute approved operations. Phoenix Core decides when a capability may run.

```text
Orchestrator -> Policy Check -> Plugin Capability -> Verification -> Event Log
```

## Read, Simulate, Mutate

Every plugin operation should be classified:

- Read: observes state without changing it.
- Simulate: computes a proposed change or dry-run result.
- Mutate: changes state.

Mutating operations must declare whether they are reversible and how to verify them.

## Versioning

Plugins should version their capability contracts. A breaking change to inputs, outputs, permissions, or behavior should create a new capability version or migration note.

## Testing Expectations

Plugins should provide:

- Unit tests for local logic.
- Contract tests for schemas and permissions.
- Simulation tests for recommended actions.
- Integration tests for safe read-only operations.
- Explicit manual test plans for risky operations.
