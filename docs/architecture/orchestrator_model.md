# Orchestrator Model

The Phoenix Orchestrator is the control plane for AI operations. It turns intent into governed, observable work.

The orchestrator coordinates workers and plugins. It should not become a monolithic business-logic application.

## Responsibilities

The orchestrator owns:

- Task intake and normalization.
- Planning and decomposition.
- Worker selection.
- Plugin capability selection.
- Permission and policy checks.
- Human approval gates.
- Event routing.
- Memory updates.
- Scheduling.
- Verification and final reporting.

## Task Lifecycle

```text
Requested
   |
   v
Scoped -> Planned -> Assigned -> In Progress -> Approval Needed
                                      |              |
                                      v              v
                                   Executing -> Verifying -> Complete
                                      |
                                      v
                                    Failed / Blocked
```

A task may return to planning after failure, review, or human feedback.

## Planning

Planning should produce:

- Objective.
- Constraints.
- Proposed steps.
- Required workers and plugins.
- Risk assessment.
- Approval points.
- Verification plan.

Plans should be explicit enough that a human can approve or reject them.

## Worker Selection

Worker selection should consider:

- Capability match.
- Required tools and environment.
- Permission scope.
- Cost and latency.
- Privacy requirements.
- Prior task performance.
- Human preference.

Codex is preferred for repository implementation tasks. Local workers may be preferred for private or offline work. Specialized plugins should handle domain-specific operations.

## Approval Gates

The orchestrator must pause before risky execution. It should emit an approval request instead of letting a worker decide alone.

Approval gate example:

```text
Action: restart Docker service
Target: synology-prod/docker/unifi-controller
Reason: apply approved network configuration
Risk: temporary service outage
Preview: service restart plan and affected containers
Rollback: restore previous compose file and restart
```

## Verification

Verification is required after execution. Verification may include:

- Tests or lint checks.
- Health checks.
- API reads.
- File or artifact inspection.
- Screenshots.
- Log checks.
- Human confirmation.

A task is not complete until verification evidence is recorded or the lack of verification is explicitly accepted.

## Scheduling

The orchestrator schedules:

- Recurring maintenance.
- Monitors and alerts.
- Deferred follow-ups.
- Periodic memory refresh.
- Long-running task continuations.

Scheduled work still obeys policy and approval rules.

## GitHub Integration

For software work, GitHub issues and PRs are first-class orchestration artifacts:

```text
Issue -> Branch -> Commits -> PR -> CI -> Review -> Merge -> Memory update
```

The orchestrator should preserve links between user intent, issue scope, implementation PRs, verification results, and architecture decisions.
