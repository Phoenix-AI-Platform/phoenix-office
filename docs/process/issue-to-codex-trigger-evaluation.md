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

## Current Verified Handoff Capabilities

Phoenix Office now has a machine-readable manual handoff spine:

- `CodexHandoffPackage` defines a deterministic package shape for preparing manual Codex work.
- `python -m phoenix_office.cli dev codex-handoff <handoff.json>` validates a handoff package fail-closed and prints a human-readable summary.
- `python -m phoenix_office.cli dev codex-handoff <handoff.json> --json` emits deterministic normalized JSON for successful packages and deterministic JSON failure payloads for missing, malformed, unreadable, or unsafe packages.
- `python -m phoenix_office.cli dev codex-handoff <handoff.json> --prompt-only` prints only the validated prompt for human copy/paste.
- `python -m phoenix_office.cli dev codex-runtime-probe` inspects the local Codex CLI surface with fixed `codex --version` and `codex exec --help` probes only.
- `python -m phoenix_office.cli dev codex-runtime-probe --json` emits the same local runtime capability report as deterministic JSON.
- The manual `Codex handoff dry-run` workflow validates a committed package with read-only repository permissions and uploads only normalized validated JSON as a temporary artifact.

These capabilities are verified as preparation, inspection, and validation surfaces only. They do not invoke Codex, create branches, open PRs, approve, merge, dispatch workflows automatically, execute orchestration plans, generate proposal/DOCX/business output, or authorize background work.

The runtime probe is intentionally local and non-invoking. It may detect whether the installed CLI advertises non-interactive `codex exec`, stdin or `-` prompt input, `--ephemeral`, `--sandbox`, `--cd` or `-C`, `--json`, `--output-last-message` or `-o`, and an explicit per-run budget-style option. It does not submit prompts, run Codex tasks, authenticate, access GitHub, access the network, inspect live branches or PRs, write files, dispatch workflows, or mutate repository state. Even if all local capabilities are detected, `pilot_ready` remains `false`; authentication, runner access, enforceable per-run budget ceilings, cancellation behavior, GitHub permissions, duplicate PR detection, branch-collision detection, actual Codex availability, final CI, and assistant review remain external checks.

## Supervised Invocation Pilot Boundary

The narrowest future pilot boundary is: a human-triggered supervised invocation that consumes one already-committed `CodexHandoffPackage` after local or workflow validation has succeeded.

This is not implemented by this document. Before any implementation PR is allowed, the mechanism must be verified in the private repository and must prove:

- the runner can read exactly the committed handoff package path selected by a human
- the runner does not need private issue-body access at invocation time
- the handoff package contains no secrets or private customer data
- one handoff maps to one issue, one branch, and one PR
- duplicate open PRs for the same issue or handoff are detected before branch creation
- changed files are limited to the handoff package's explicit low-risk allowed paths
- validation commands are deterministic and recorded in the PR body
- the PR body preserves the required headings and links the source issue
- Codex stops after opening the PR and must never approve or merge its own PR
- assistant review remains required; if the assistant review verdict is MERGE and CI passes, the assistant may perform the routine merge
- human authority remains required for policy, risk-boundary, eligibility, permission, credential, and automation-scope changes

The first eligible pilot class should be exactly one docs-only objective under already-reviewed process/development documentation paths. The pilot cap should be no more than three Markdown files total, limited to `docs/process/**/*.md` and `docs/development/**/*.md`. Runtime code, tests, workflows, fixtures, examples, JSON data, templates, package files, lock files, schemas/models, proposal/DOCX/business-output behavior, orchestration behavior, API/MCP/server/worker/background behavior, and uncertain-risk tasks must remain manual prompt handoff only.

Required source issue fields before invocation:

- source issue number and URL
- issue title
- risk class, which must be `docs-only` for the first pilot
- repository, which must be `Phoenix-AI-Platform/phoenix-office`
- expected PR title
- allowed paths, limited to `docs/process/**/*.md` and `docs/development/**/*.md`
- strict out-of-scope boundaries
- required validation commands
- required PR body headings
- explicit statement that Codex invocation does not authorize approval, merge, workflow dispatch, proposal/DOCX generation, orchestration execution, or background work

Required `CodexHandoffPackage` fields before invocation:

- `schema_version`
- `handoff_id`
- task identity fields, including `task.task_id`, `task.title`, and `task.objective`
- source issue identity carried by the task context or prompt
- `repository`, which must be `Phoenix-AI-Platform/phoenix-office`
- `base_branch`, which must equal `main`
- `expected_pr_title`
- `prompt`, containing the scoped Codex-ready objective
- `required_repo_paths`, capped to no more than three eligible Markdown files under `docs/process/**/*.md` and `docs/development/**/*.md`
- `required_pr_body_headings`
- validation plan naming the package validation and repository validation commands
- safety flags: `invocation_authorized: false`, `invocation_mode: "manual"`, `review_required: true`, and `worker_may_merge: false`

Credentials and permissions for any later pilot must be minimal:

- read access to the repository contents needed to load the package
- branch and pull-request creation only if the pilot implementation explicitly requires it
- no repository administration permissions
- no secret values in issues, PR bodies, logs, artifacts, or comments
- no personal access token unless a dedicated reviewed security decision proves the built-in token is insufficient

Cost and usage controls must be explicit before implementation:

- human-triggered only
- one package path per run
- one attempt per selected handoff
- no automatic retries
- hard maximum runtime of 30 minutes per pilot run
- a platform-supported budget or usage ceiling must be configured before invocation; if the platform cannot enforce a ceiling, the pilot must fail closed before invocation
- operator cancellation must immediately stop further work; after cancellation, the pilot must not approve, merge, comment, label, dispatch workflows, launch follow-up activity, retry, schedule, or continue in the background
- no hidden polling, scheduling, retries, queues, or background workers
- clear logs that show the handoff id, issue id, branch name, PR URL, validation summary, and stop reason without exposing prompt secrets or private data

Failure must be closed and observable:

- missing package, invalid package, unsafe package, unsupported risk class, ambiguous paths, duplicate PR, branch collision, validation failure, uncertain credentials, or private-data risk means no Codex invocation or no PR creation
- if invocation starts but cannot complete safely, it must stop without approval, merge, workflow dispatch, retries, or follow-up automation
- manual pasted-prompt handoff remains supported whenever the supervised path is unavailable or uncertain

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
- bypass CI, assistant review, or human authority over risky policy and scope changes
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

### Human-Triggered Validated Handoff Invocation

Status: recommended first pilot candidate, but unimplemented and still requires verification.

Trigger: a human selects a committed `CodexHandoffPackage` and starts a supervised invocation from a reviewed entry point after the package passes `dev codex-handoff` validation.

Credentials/access needed:

- repository contents read access for the selected package
- any Codex runner credentials required by the invocation mechanism
- branch and PR creation permissions only if the pilot will open a PR directly

Private issue access: not required at invocation time if the handoff package already carries the reviewed issue context. This is safer than issue-event triggers because it avoids assuming Codex can read private issue bodies.

Allowed actions if later implemented:

- validate one committed handoff package
- create one branch for the linked issue
- apply only the scoped documentation change requested by the handoff
- open one PR linked back to the issue
- stop after opening the PR
- wait for assistant review; if the assistant review verdict is MERGE and CI passes, the assistant may perform the routine merge

Must not be allowed to:

- run from issue text that has not been packaged and validated
- select additional files outside the handoff allowed paths
- invoke Codex for runtime, execution, API/MCP/server/background, schema/model, proposal/DOCX/business-output, or uncertain-risk work
- approve, merge, label, comment, dispatch workflows, retry, schedule, queue, or run in the background

PR opening: one branch and one PR, named from the validated handoff, with duplicate-PR detection before branch creation. The PR body must link the issue and include required headings, validation, and out-of-scope confirmations. The PR base must be `main`; any other `base_branch` fails closed before branch creation.

One-issue/one-PR scope: the package's issue id, handoff id, branch name, and expected PR title must bind together. If any binding conflicts with an existing open PR or branch, fail closed.

Fail-closed behavior: no package, invalid package, unsafe package, unsupported risk class, duplicate PR, ambiguous changed-file boundary, missing validation, credential uncertainty, or private-data risk means no invocation.

Suitability: suitable as the first candidate only for documentation-only process/development tasks after a separate reviewed implementation PR. It is safer than mention, assignment, or issue-event workflows because the human selects an already-validated package and the runner does not need to infer task authority from live issue text.

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

Suitability: suitable now for docs-only and carefully scoped manual tasks. Riskier classes remain manual prompt handoff only unless a later reviewed policy changes that boundary; Codex still stops after opening a PR, and routine merge execution follows assistant review and passing CI.

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
- uncertain risk fails closed before invocation or PR creation
- generated files are not changed unless explicitly scoped and reviewed
- `CodexHandoffPackage` validation must pass before invocation
- the exact package path must be human-selected
- duplicate branch or PR detection must run before mutation
- changed-file limits must be enforced before PR creation and rechecked in review
- `base_branch` must equal `main`
- assistant review remains required before routine merge; Codex must never approve or merge its own PR

Required package validation commands:

```bash
python -m phoenix_office.cli dev codex-handoff <handoff.json>
python -m phoenix_office.cli dev codex-handoff <handoff.json> --json
python -m phoenix_office.cli dev codex-handoff <handoff.json> --prompt-only
```

Required repository validation commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp
python -m ruff check . --no-cache
git diff --check
```

The pilot must enforce the docs-only changed-file cap before PR creation and the assistant review must recheck the same cap before any merge verdict.

## Required Staged PR Sequence

Any supervised invocation pilot must be implemented one narrow PR at a time:

1. Documentation decision PR: record the selected mechanism, permissions, risk class, failure modes, and validation evidence.
2. Read-only dry-run PR: validate package selection, duplicate detection, changed-file eligibility, and credential assumptions without invoking Codex or creating branches.
3. Prompt construction PR: produce the exact invocation prompt or request payload from the validated package without sending it.
4. Supervised invocation pilot PR: allow a human-triggered invocation for documentation-only packages; the pilot itself must not approve, merge, comment, label, retry, schedule, queue, or run background behavior.
5. Validation PR: run a tiny docs-only package through the pilot and record observed behavior before considering any expansion.

Each PR must keep its own scope narrow. Auto-merge, issue-event triggers, PR comments, label mutation, branch updates, workflow dispatch from issues, broader file paths, runtime code, proposal/DOCX behavior, and orchestration execution require separate reviewed decisions.

## Recommended Next Decision

Keep the manual pasted-body fallback as the default path.

The recommended first pilot candidate is human-triggered validated handoff invocation from one committed `CodexHandoffPackage`, limited to documentation-only process/development tasks. This boundary is safer than `@codex` mention, issue assignment, or issue-event workflow triggers because it relies on a reviewed package contract, does not require live private issue access by Codex, and leaves the human in control of when invocation starts.

Do not implement invocation from this document. A pilot should only be implemented in later dedicated PRs after the mechanism, credentials, permissions, branch/PR creation behavior, duplicate detection, changed-file enforcement, cost controls, audit evidence, and fail-closed behavior are verified in the private repository.

Runtime, execution, API/MCP/server/background, DOCX/proposal/business-output, schema/model, and uncertain-risk tasks should remain manual prompt handoff only until a later reviewed policy explicitly changes that boundary.

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
