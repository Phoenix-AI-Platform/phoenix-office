# Security Model

Phoenix is designed for human-governed automation. Security is not an add-on; it is part of the operating model.

## Core Rule

Risky execution requires approval before action.

Risky execution includes:

- Destructive file operations.
- Infrastructure changes.
- Network configuration changes.
- Credential or secret changes.
- Production deployments.
- External communications.
- Financial or customer-impacting actions.
- Operations that are difficult to reverse.

## Permission Model

Permissions should be explicit and scoped:

```text
subject: worker or plugin
capability: operation being requested
resource: target file, repo, device, host, service, or account
mode: read, simulate, write, execute, destructive
conditions: environment, approval, time, policy, human owner
```

Workers should receive the least privilege needed for the task.

## Approval Record

An approval record should include:

- Who approved.
- What was approved.
- When approval happened.
- Target resources.
- Risk level.
- Preview or simulation evidence.
- Expiration or one-time-use scope when applicable.

Approvals are audit events.

## Secrets

Secrets should be brokered by Phoenix Core or a vault. Workers and plugins should receive secret handles or scoped tokens when possible, not long-lived raw secrets.

Secret handling rules:

- Never log raw secrets.
- Never store raw secrets in ordinary memory.
- Prefer short-lived credentials.
- Scope credentials to the target operation.
- Rotate credentials after suspected exposure.

## Policy Checks

Before execution, Phoenix should check:

- Does the worker have permission for this operation?
- Does the plugin capability require approval?
- Is the target environment protected?
- Is the action reversible?
- Is simulation available and current?
- Are required verification steps defined?

Policy failures should stop execution and return a structured reason.

## Audit And Logging

Security-sensitive actions must emit logs and audit events. Logs should be useful without exposing secrets.

Audit records should connect:

```text
intent -> plan -> approval -> execution -> verification -> result
```

## Sandboxing

Workers should run in constrained environments when practical. Sandboxing may include filesystem limits, network limits, command allowlists, tool-specific approval, and environment isolation.

## Human Override

Humans can override policy only through explicit approval records. Overrides should include reason, scope, and expiration.
