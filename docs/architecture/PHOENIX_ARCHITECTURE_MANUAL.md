# Phoenix Architecture Manual

Phoenix is an AI Operations Platform: an operating system for coordinating AI workers, plugins, tools, repositories, infrastructure, and human approval.

Phoenix is not a monolithic AI model. It is not only a UniFi optimizer. It is not only an office automation app. Phoenix is the coordination layer that lets many AI and automation capabilities work safely across many operational domains.

## Mission

Phoenix turns human intent into governed work. It accepts tasks, routes them to workers and plugins, preserves context, asks for approval before risky execution, verifies outcomes, and records what happened.

The platform should support Office, UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud services, local tools, and future plugins without making any one domain the center of the architecture.

## System Shape

```text
Human / ChatGPT Architect / GitHub Issues
              |
              v
        Phoenix Orchestrator
              |
   +----------+----------+------------------+
   |          |          |                  |
Memory    Event Bus  Permissions        Scheduler
   |          |          |                  |
   +----------+----------+------------------+
              |
              v
       Worker + Plugin Runtime
              |
   +----------+----------+------------------+
   |          |          |                  |
Codex     Unity AI   Local LLMs       Future Agents
Office    UniFi      Home Assistant   Docker / Cloud
Plugins   Plugins    Plugins          Plugins
```

Phoenix Core owns cross-cutting platform services. Plugins expose capabilities. Workers perform tasks. Humans approve risky steps. GitHub issues and PRs provide durable task records.

## Core Loop

All non-trivial work follows this loop:

```text
Observe -> Analyze -> Recommend -> Simulate -> Approve -> Execute -> Verify
```

- Observe: collect state from tools, repos, infrastructure, devices, logs, or user input.
- Analyze: interpret the state and identify candidate actions.
- Recommend: present a proposed plan, risk level, and expected outcome.
- Simulate: dry-run or preview changes when possible.
- Approve: require a human or policy approval for risky work.
- Execute: perform the approved action through a worker or plugin.
- Verify: check the result, record evidence, and report completion or failure.

Skipping steps is allowed only for low-risk read-only or explicitly pre-approved work.

## Platform Responsibilities

Phoenix Core provides:

- Memory: durable knowledge, task history, decisions, approvals, and environment facts.
- Event bus: task events, worker status, plugin events, approval requests, and audit events.
- Configuration: platform, plugin, worker, environment, and policy settings.
- Secrets: credential references and access brokering without exposing raw secrets to workers unnecessarily.
- Permissions: policy checks for read, write, execute, network, infrastructure, and destructive actions.
- Logging: structured logs, audit records, and verification evidence.
- Scheduling: recurring tasks, monitors, reminders, and deferred execution.

Phoenix Core does not contain every domain-specific workflow. Domain behavior belongs in plugins and workers.

## Workers

Workers are external or embedded executors coordinated by Phoenix. Codex, Unity AI, local LLMs, browser automation, shell runners, and future agents are workers from Phoenix's point of view.

Workers can:

- Receive tasks with context, constraints, and expected outputs.
- Report progress and intermediate findings.
- Request more context or human approval.
- Fail with structured reasons.
- Retry when policy allows.
- Return results and verification evidence.

Workers must not silently exceed their permission scope.

## Plugins

Plugins expose consistent capabilities to the orchestrator. A plugin may wrap APIs, local tools, infrastructure, or domain logic.

A plugin should describe:

- Capabilities it provides.
- Inputs, outputs, and validation rules.
- Required permissions and secrets.
- Read-only versus mutating operations.
- Simulation or dry-run support.
- Verification methods.
- Failure modes and retry behavior.

Examples include Office, UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud, and repository plugins.

## Orchestrator

The orchestrator is the control plane. It converts intent into tasks, selects workers and plugins, enforces policy, tracks state, and ensures work reaches a verified outcome.

The orchestrator should not be a giant domain script. It should coordinate components through stable contracts.

```text
Task Request
   |
   v
Plan -> Select Worker/Plugin -> Policy Check -> Approval Gate
   |                                      |
   v                                      v
Events + Memory <-------------------- Execution
   |
   v
Verification -> Result -> GitHub / Human Report
```

## Approval And Safety

Human approval is required before risky execution. Risky execution includes destructive file operations, infrastructure changes, credential changes, production changes, financial transactions, external communications, and any action whose effect cannot be easily reversed.

Approval requests should include:

- The proposed action.
- The target system or resource.
- The reason for the action.
- The expected result.
- Known risks and rollback options.
- A dry-run or preview when available.

Approval decisions are stored as audit events.

## Memory Model

Phoenix memory is not just chat history. It is operational state. It should separate:

- Facts: stable environment, repository, device, customer, and infrastructure facts.
- Events: task lifecycle, worker progress, approvals, errors, and verification records.
- Decisions: architectural choices, policies, and accepted tradeoffs.
- Artifacts: generated documents, patches, reports, logs, and links.
- Preferences: human operating preferences and recurring constraints.

Memory must be permission-aware. Workers receive only the memory needed for the task.

## GitHub Task Lifecycle

GitHub issues and PRs are part of Phoenix operations. A normal software task lifecycle is:

```text
ChatGPT architect defines intent
        |
        v
GitHub issue captures scope and acceptance criteria
        |
        v
Codex implementation worker creates branch and PR
        |
        v
CI, review, and human approval
        |
        v
Merge, release note, memory update
```

Issues define the desired outcome. PRs provide the implementation record. CI and review provide verification evidence.

## ChatGPT And Codex Roles

ChatGPT acts as architect, product partner, and operations planner. It clarifies goals, writes issues, defines acceptance criteria, reviews tradeoffs, and maintains architecture direction.

Codex acts as implementation worker. It reads the issue, inspects the repo, changes files, runs tests, reports progress, opens PRs, and records verification.

This separation keeps strategy and execution connected without making either role overloaded.

## Design Principles

- Platform over app: Phoenix coordinates many domains, not one feature set.
- Human-governed autonomy: automation expands capability but does not bypass approval.
- Stable contracts: workers and plugins integrate through explicit capability boundaries.
- Observable execution: every important action emits events and verification evidence.
- Minimal privilege: workers receive only the access needed for the task.
- Simulation first: preview changes before execution whenever practical.
- Recovery-aware design: failures should be explicit, diagnosable, and retryable.
- Documentation before expansion: major runtime systems should start with documented contracts.

## Repository Implications

This repository can host Phoenix Office code and Phoenix architecture documentation while the platform is still forming. Runtime code should not be forced into Phoenix Core until the contracts are clear.

Near-term changes should favor:

- Clear plugin boundaries.
- Small capability modules.
- Testable workers and helpers.
- Issue-driven development.
- Explicit approval points for risky operations.

## Supporting Documents

- [Worker Model](worker_model.md)
- [Plugin Model](plugin_model.md)
- [Memory Model](memory_model.md)
- [Orchestrator Model](orchestrator_model.md)
- [Security Model](security_model.md)
- [Development Process](development_process.md)
- [Roadmap](roadmap.md)
