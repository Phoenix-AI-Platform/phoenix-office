# Issue-to-Codex Trigger Evaluation

## Purpose

This document records a documentation-only evaluation of possible paths for turning Phoenix task issues into Codex work.

The goal is to reduce manual prompt pasting eventually, while preserving one-issue/one-PR scope, human review, and human authority over risky changes.

This document does not implement a trigger, GitHub Actions workflow, auto-merge behavior, background worker, API, MCP, server behavior, execution behavior, or repository mutation behavior.

## Current Observation

The current workflow has separate access contexts:

- ChatGPT can create and inspect private GitHub issues through its GitHub connector.
- Codex, in the observed session, could not read private issue `#141` directly.
- Codex required the issue body to be pasted manually.

Therefore, ChatGPT GitHub connector access and Codex GitHub issue access must not be assumed to be the same. Any issue-to-Codex trigger path must be verified before implementation.

## Candidate Trigger Paths

### `@codex` Mention On An Issue Or Comment

Status: unverified.

Trigger: a human or assistant comments on a Phoenix task issue with an `@codex` mention, or includes the mention in the issue body.

Credentials/access needed: a Codex-side GitHub integration able to receive mention events and read the private repository issue body, comments, labels, and linked context.

Private issue access: unverified. This must be proven in the private `Phoenix-AI-Platform/phoenix-office` repository before any implementation depends on it.

Allowed actions if supported:

- read the Phoenix task issue body and comments
- create one branch for the issue
- open one PR linked back to the issue
- report validation status in the PR body or PR comments if explicitly scoped later

Must not be allowed to:

- execute orchestration plans
- generate business output
- generate DOCX/proposal files automatically
- mutate approvals, rejections, plans, or reviews
- bypass CI, assistant review, or human merge authority
- expose secrets or private customer data in logs, comments, artifacts, issues, or PR bodies
- auto-merge in the same trigger flow

PR opening: Codex would need to create a branch and PR through a verified GitHub integration. The PR must link back to the issue and include the required PR body headings.

One-issue/one-PR scope: the trigger must bind exactly one issue to one branch and one PR. If the issue references multiple unrelated changes, the trigger must fail closed or request issue splitting.

Fail-closed behavior: if the mention is unsupported, the issue cannot be read, risk is uncertain, allowed paths are unclear, or guardrails conflict, no PR should be opened.

Suitability: potentially suitable for docs-only tasks after verification. Not suitable for code, execution-adjacent, DOCX/proposal/business-output, runtime/model/schema, API/MCP/server/background, or uncertain-risk tasks until additional reviewed safeguards exist.

### GitHub Issue Assignment To Codex Or Agent Identity

Status: unverified.

Trigger: a Phoenix task issue is assigned to a Codex or agent identity.

Credentials/access needed: an agent identity with permission to receive assignment events, read private issues, create branches, and open PRs in the private repository.

Private issue access: unverified. Assignment visibility does not prove private issue body access.

Allowed actions if supported:

- read the assigned Phoenix task issue
- verify task fields and risk class
- create one branch and one PR for the assigned issue
- leave status only if a later dedicated PR explicitly permits comments

Must not be allowed to:

- mutate issue content, labels, approvals, plans, or reviews
- trigger execution, workers, queues, scheduling, retries, or background behavior
- generate DOCX/proposal/business output
- auto-merge or bypass human authority
- use issue assignment as approval for risky changes

PR opening: the agent would open a PR with the expected title from the issue, link the issue, and preserve the issue guardrails in the PR body.

One-issue/one-PR scope: one assignment should map to one branch and one PR. Reassignment or multiple assigned issues must not cause bundled work.

Fail-closed behavior: if assignment events are unavailable, the agent cannot read the issue, or the issue fields are incomplete, no PR should be opened.

Suitability: potentially suitable for docs-only tasks after verification. Not suitable for higher-risk task classes until explicit reviewed policy and safeguards exist.

### GitHub Actions Workflow Invoking Codex CLI Or Agent Runner

Status: unverified and higher risk.

Trigger: a GitHub Actions workflow runs on issue events or issue comments and invokes a Codex CLI or agent runner.

Credentials/access needed:

- GitHub Actions token or GitHub App token with private issue read access
- credentials for any Codex or agent runner
- branch and PR creation permissions
- carefully scoped secret handling

Private issue access: possible in principle with the right token, but unverified for a Codex runner in this repository.

Allowed actions if ever implemented:

- read a Phoenix task issue that passes strict filters
- run only for explicitly allowed low-risk classes
- create one branch and one PR
- surface validation results without exposing secrets

Must not be allowed to:

- run arbitrary issue text as shell commands
- expose tokens, secrets, private data, logs, artifacts, or comments
- enqueue, schedule, retry, or run background work beyond the reviewed workflow
- execute orchestration plans
- mutate approvals, rejections, plans, or reviews
- generate business output or DOCX/proposal files automatically
- include auto-merge in the same PR as the trigger implementation

PR opening: the workflow would need a reviewed, minimally scoped branch/PR creation mechanism. It must include issue linkage, required PR body headings, changed-file limits, and validation reporting.

One-issue/one-PR scope: the workflow must reject tasks that name multiple unrelated scopes, ambiguous allowed paths, or multiple target PRs.

Fail-closed behavior: missing labels, unsupported risk class, missing required fields, duplicate active PRs, secrets in the issue body, private customer data, or uncertain risk must stop the workflow before branch creation.

Suitability: not suitable yet. It may be considered later for docs-only tasks, but only after a dedicated reviewed workflow-design PR, threat model, tests, and secret-handling review.

### Manual Or Semi-Automatic Pasted-Body Fallback

Status: currently verified by observation.

Trigger: ChatGPT creates or reviews a Phoenix task issue, then the user or assistant pastes the issue body into Codex manually.

Credentials/access needed: ChatGPT GitHub connector access for issue creation/review, plus the user's active Codex session. Codex does not need direct private issue read access because the body is supplied manually.

Private issue access: ChatGPT connector access exists in the observed workflow. Codex private issue access remains unnecessary for this fallback.

Allowed actions:

- ChatGPT may create and inspect the issue through its connector when authorized.
- The user or assistant may paste the issue body into Codex.
- Codex may open one narrow PR from the pasted instructions.

Must not be allowed to:

- treat pasted issue text as permission to bypass scope guardrails
- execute plans, generate business output, mutate approvals/reviews, or auto-merge
- include secrets or private customer data in pasted task text
- bundle multiple issues into one PR

PR opening: Codex opens a PR using the pasted issue body as the task prompt and links the issue if the issue URL or number is provided.

One-issue/one-PR scope: preserved by human handoff. The human or assistant should paste one issue body at a time.

Fail-closed behavior: if the issue is ambiguous, risky, missing guardrails, or contains secrets/private customer data, no implementation PR should be opened until the issue is corrected.

Suitability: suitable now for docs-only and carefully scoped manual tasks. Riskier classes remain human-review and human-merge only.

## Required Safety Gates Before Any Trigger Implementation

Any future trigger implementation must preserve these gates:

- no automatic execution behavior
- no automatic business output generation
- no automatic DOCX/proposal generation
- no background worker that bypasses review
- no auto-merge in the same PR as a trigger
- no secrets exposed in issue bodies, PR bodies, logs, artifacts, or comments
- no private customer data in tasks
- no ability to mutate approvals, rejections, plans, or reviews
- no runtime, API, MCP, server, worker, or background behavior unless explicitly scoped in a later dedicated PR
- one issue maps to one branch and one PR
- uncertain risk fails closed to manual review and manual merge
- generated files are not changed unless explicitly scoped and reviewed

## Recommended Next Decision

Keep the manual pasted-body fallback until a verified trigger mechanism exists.

Do not implement an issue-to-Codex trigger from this document. A trigger should only be implemented in a later dedicated PR after the mechanism is confirmed in the private repository and its credentials, event model, permissions, and fail-closed behavior are understood.

If a trigger becomes available, start with docs-only tasks. Runtime, execution, API/MCP/server/background, DOCX/proposal/business-output, schema/model, and uncertain-risk tasks should remain manual-review and manual-merge only until a later reviewed policy explicitly changes that boundary.

## Non-Goals

This evaluation does not add or authorize:

- GitHub Actions workflows
- issue-to-Codex trigger behavior
- auto-merge behavior
- label creation or repository mutation behavior
- execution behavior
- orchestration `execute`, `run`, `apply`, `approve`, or `reject`
- plan or review mutation
- DOCX generation or rendering changes
- proposal generation changes
- pricing, scope, notes, item description, or customer data inference
- audit persistence, output artifacts, queues, scheduling, or retries
- API, MCP, server, worker, or background behavior
