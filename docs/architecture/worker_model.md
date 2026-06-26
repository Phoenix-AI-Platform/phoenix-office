# Worker Model

Workers are execution units coordinated by Phoenix. A worker may be an AI coding agent, a local LLM, a browser automation agent, a Unity agent, a shell runner, or a future specialized service.

Workers are not trusted to act without boundaries. Phoenix gives workers tasks, context, permissions, and expected outputs.

## Worker Contract

A worker should support this lifecycle:

```text
Assigned -> Accepted -> In Progress -> Needs Approval -> Executing -> Verifying -> Complete
                         |                 |              |
                         v                 v              v
                     Blocked            Failed          Failed
```

Required worker behaviors:

- Accept or reject a task with a reason.
- Report progress during long-running work.
- Ask for clarification when the task cannot be completed safely.
- Request approval before risky execution.
- Return structured failure information.
- Retry only when policy allows.
- Return final artifacts, logs, and verification evidence.

## Task Envelope

Phoenix should send workers a task envelope containing:

- Task id and title.
- Goal and acceptance criteria.
- Allowed repositories, files, tools, and environments.
- Relevant memory and prior decisions.
- Permission limits.
- Approval requirements.
- Expected result format.
- Verification commands or checks.

Workers should not infer broad access from vague task language.

## Worker Types

Initial worker types:

- Codex: repository implementation, tests, refactors, PR creation, issue execution.
- ChatGPT architect: requirements, planning, review, issue definition, architecture direction.
- Unity AI worker: game/editor workflows, scene analysis, asset and script tasks.
- Local LLM worker: private/offline reasoning, classification, summarization, local automation.
- Browser worker: web workflows, UI inspection, screenshots, and browser verification.
- Infrastructure worker: Docker, Linux, Windows, Synology, cloud, and Home Assistant operations.

Phoenix coordinates these workers through common task and event contracts.

## Progress Reporting

Progress events should be small and useful:

```text
worker.started
worker.progress
worker.approval_requested
worker.blocked
worker.failed
worker.completed
worker.verified
```

Progress should identify what changed, what was learned, and what remains.

## Failure Model

Workers fail in predictable categories:

- missing_context: required information is unavailable.
- permission_denied: requested action exceeds current permission.
- tool_unavailable: a required tool or service cannot be reached.
- validation_failed: tests, checks, or verification failed.
- execution_failed: an approved operation failed during execution.
- policy_blocked: platform policy forbids the action.

Failures should include evidence and a recommended next action.

## Retry Rules

Retries are allowed when:

- The action is idempotent.
- The failure is transient.
- The retry stays within permission scope.
- The retry does not hide a validation failure.

Retries require renewed approval when the next attempt changes the risk profile.

## Worker Boundaries

Workers should not own platform memory, secrets, global permissions, or scheduling. Those belong to Phoenix Core. Workers may cache local context during a task, but Phoenix decides what is durable.
