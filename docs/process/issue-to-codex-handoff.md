# Issue-to-Codex Preparation Handoff

## Purpose

This note defines a manual, reviewable handoff format for turning a Phoenix task issue into a Codex-ready prompt.

The handoff reduces repeated prompt assembly, but it does not invoke Codex automatically. A human operator remains responsible for deciding when to start Codex, what prompt to paste, and whether the active workspace is correct.

This process is documentation only. It does not add workflow behavior, CI behavior, issue-to-Codex automation, Codex API calls, GitHub Actions Codex invocation, comments, labels, approvals, branch updates, auto-merge eligibility changes, runtime behavior, persistence, or background work.

## Handoff Boundary

A Phoenix task issue is task context, not executable authority.

Codex should treat the handoff as a scoped implementation request that is still constrained by:

- `AGENTS.md`
- current project state
- the explicit issue scope
- repository guardrails
- PR body requirements
- validation expectations
- human review and merge authority

If the issue body conflicts with repository guardrails, the stricter safety boundary wins. If risk is uncertain, the operator should stop and clarify the issue before starting Codex.

## Operator Checklist

Before starting Codex from a Phoenix task issue, the operator should confirm:

- the issue number and title are correct
- the target repository is `Phoenix-AI-Platform/phoenix-office`
- the active checkout is the intended Phoenix Office checkout
- the current branch starts from latest `main`
- expected Phoenix files exist, such as `.github/workflows/docs_only_auto_merge.yml` when workflow context matters and `src/phoenix_office/` for repo identity
- the task risk class is clear
- allowed files or suggested files are explicit
- strict out-of-scope boundaries are present
- validation commands are listed
- expected PR title is present
- required PR body headings are listed
- review and merge expectations are explicit
- the issue contains no secrets or private customer data
- the task maps to one issue, one branch, and one PR

If any item is missing, the operator should update or clarify the issue before starting Codex.

## Handoff Format

A Codex handoff should include these sections in order:

1. Verified workspace
2. Repository identity
3. Issue number and title
4. Goal
5. Scope
6. Suggested or allowed files
7. Strict out-of-scope boundaries
8. Validation commands
9. PR title and body requirements
10. Review and merge expectations
11. Wrong-workspace guardrails
12. Acceptance criteria

The handoff should be self-contained enough that Codex does not need to infer the repository, branch, risk class, validation commands, or PR body shape.

## Machine-Readable Handoff Package

`CodexHandoffPackage` is the machine-readable form of this handoff. It wraps an existing `TaskEnvelope` and keeps that envelope as the source of task intent, scope, constraints, acceptance criteria, context references, allowed resources, permissions, approval policy, and verification commands.

The package adds only Codex-specific preparation metadata:

- repository and base branch identity
- verified workspace path expectations
- required repository identity paths
- expected PR title and required PR body headings
- the self-contained Codex prompt to paste manually
- worker, review, and invocation boundaries

Creating, reading, validating, displaying, or reviewing a `CodexHandoffPackage` does not invoke Codex, fetch GitHub issues, trigger workflows, run workers, or perform background behavior.

`invocation_authorized: false` means the package is preparation only. A human still decides whether to start Codex and what prompt to paste. `worker_may_merge: false` means Codex must stop after opening its PR; reviewer approval and the repository merge process remain separate human-controlled gates.

Operators can inspect a package in human-readable form:

```bash
python -m phoenix_office.cli dev codex-handoff examples/tasks/codex_handoff_package.json
```

They can also inspect the same package as deterministic machine-readable JSON:

```bash
python -m phoenix_office.cli dev codex-handoff examples/tasks/codex_handoff_package.json --json
```

When `--json` is supplied, missing paths, malformed JSON or UTF-8, and unsafe packages return nonzero with deterministic JSON on stdout. The failure payload includes `ok: false`, an `error_code`, a human-readable `message`, the checked `path`, and any validation `issues`. Without `--json`, the command keeps the human-readable stderr failure messages.

After validation succeeds, operators can print only the package prompt for manual copy/paste:

```bash
python -m phoenix_office.cli dev codex-handoff examples/tasks/codex_handoff_package.json --prompt-only
```

`--prompt-only` cannot be combined with `--json`.

The inspection command is read-only. It reads one local JSON file, validates the current v1 safety boundary, and prints either a text summary, sorted indented JSON, or only the validated prompt. It does not create or rewrite packages, invoke Codex, call GitHub APIs, dispatch workflows, execute workers, mutate files, or merge a PR.

The command fails closed for malformed, incomplete, unsupported, or unsafe packages. A successful inspection means only that the package satisfies the current read-only handoff checks; it does not authorize Codex invocation, PR approval, merge behavior, proposal generation, DOCX rendering, or any background work.

## Static Invocation Preflight

Operators can run a read-only static preflight for the supervised invocation pilot boundary:

```bash
python -m phoenix_office.cli dev codex-invocation-preflight examples/tasks/codex_handoff_package.json
```

They can also emit the same report as deterministic JSON:

```bash
python -m phoenix_office.cli dev codex-invocation-preflight examples/tasks/codex_handoff_package.json --json
```

The preflight reuses the fail-closed `CodexHandoffPackage` validation and then checks the package against the docs-only pilot rules: repository `Phoenix-AI-Platform/phoenix-office`, `base_branch: "main"`, `docs-only` task risk, strict JSON-false task permissions for destructive, execution, and network access, exactly one to three unique safe repository-relative Markdown files in `task.allowed_resources.paths` under `docs/process/` or `docs/development/`, membership of every `required_repo_paths` entry in that allowed-resource boundary, required PR headings, and required repository validation commands.

The preflight is static only. It does not invoke Codex, access GitHub, fetch issues, inspect live PRs or branches, create artifacts, write files, dispatch workflows, execute workers, or mutate anything.

The report includes the handoff ID, source issue number, repository, base branch, and declared changed files. `declared_changed_files` is reported from the validated `task.allowed_resources.paths` boundary because that is the package's static write boundary; `required_repo_paths` must remain a subset of it. The report also separates:

- static eligibility
- package blockers
- external checks still required

External checks still required include duplicate PR detection, branch collision detection, repository credentials and permissions, budget or usage ceiling enforcement, operator cancellation support, Codex availability, post-PR CI, and assistant review before merge.

A static eligible result never authorizes invocation. It means only that the package currently satisfies the local static checks for possible later supervised review.

## Invocation Request Draft

Operators can turn a statically eligible docs-only handoff package into a deterministic provider-neutral request draft:

```bash
python -m phoenix_office.cli dev codex-invocation-request <path-to-statically-eligible-docs-handoff.json>
```

They can also emit the draft as sorted, indented JSON:

```bash
python -m phoenix_office.cli dev codex-invocation-request <path-to-statically-eligible-docs-handoff.json> --json
```

The request command reuses the complete static invocation preflight. If the package is missing, malformed, unsafe, or statically ineligible, no request draft and no rendered prompt are produced. JSON failures include the preflight blockers and remain non-authorizing.

When static preflight succeeds, the command prints one local stdout-only draft. The draft includes identity, source issue number, repository, base branch, expected PR title, declared changed files, required PR body headings, required repository validation commands, the original reviewed package prompt, a deterministic rendered prompt, and the external checks still required.

The draft is unsent. It does not invoke Codex, call a provider API, access GitHub, fetch issues, inspect live PRs or branches, create branches, open PRs, write files, create artifacts, dispatch workflows, execute workers, approve, merge, retry, schedule, queue, persist state, or continue in the background.

The draft does not authorize Codex invocation. It remains provider-neutral preparation for later supervised review, and it does not claim duplicate-PR detection, branch-collision detection, credentials, budget enforcement, cancellation support, Codex availability, final CI, or assistant review have passed.

## Manual Dry-Run Workflow

Operators can run the `Codex handoff dry-run` workflow manually from GitHub Actions when they want CI to validate a committed handoff package.

The workflow has only a `workflow_dispatch` trigger. Its required `handoff_path` input must be a repository-relative path to a committed `CodexHandoffPackage` JSON file, such as:

```text
examples/tasks/codex_handoff_package.json
```

The workflow checks out the selected ref, installs Phoenix Office with the repository-supported Python setup, safely resolves the requested path inside the workspace, and validates the package with:

```bash
python -m phoenix_office.cli dev codex-handoff <resolved-handoff-path>
python -m phoenix_office.cli dev codex-handoff <resolved-handoff-path> --json
```

Only the normalized validated JSON is uploaded, as artifact `codex-handoff-dry-run`, with a 7-day retention period. The normalized JSON is written under runner temporary storage, not into the tracked repository tree.

The dry-run workflow does not invoke Codex, call GitHub APIs, dispatch other workflows, approve PRs, merge PRs, create comments, mutate labels, update branches, or perform any other GitHub mutation. It is preparation and validation only.

### Validation Record

The manual workflow boundary was validated on `main` after PR #264 merged:

- Successful run: [28631252154](https://github.com/Phoenix-AI-Platform/phoenix-office/actions/runs/28631252154) used `examples/tasks/codex_handoff_package.json`. The validation, text inspection, normalized JSON write, artifact upload, and summary steps all completed successfully.
- The successful run uploaded exactly one artifact named `codex-handoff-dry-run`. The artifact contained `codex-handoff-package.json`, retained the expected normalized safety fields including `invocation_authorized: false`, `invocation_mode: "manual"`, `review_required: true`, and `worker_may_merge: false`, and was configured to expire after 7 days.
- Unsafe-path run: [28631594213](https://github.com/Phoenix-AI-Platform/phoenix-office/actions/runs/28631594213) used `../codex_handoff_package.json`. It failed in `Resolve handoff path safely`; inspection, normalized JSON generation, artifact upload, and summary were skipped.
- The unsafe-path run uploaded no artifacts.

These runs verify the intended fail-closed boundary without authorizing or performing Codex invocation, GitHub mutation, PR approval, or merge behavior.

Future CLI commands, workflow behavior, issue fetching, package validation automation, or Codex invocation behavior require separate reviewed PRs.

## Reusable Codex Prompt Template

```text
Use the verified Phoenix Office checkout only:
C:\tmp\phoenix-office

Repo:
Phoenix-AI-Platform/phoenix-office

Issue:
#<issue-number> - <issue-title>

Before editing, confirm:
- repo remote is Phoenix-AI-Platform/phoenix-office
- current branch starts from latest main
- expected repo identity files exist
- src/phoenix_office/ exists

Goal:
<one concise goal statement from the issue>

Scope:
- <allowed change category>
- <specific required changes>
- <documentation/test/runtime classification>

Suggested files:
- <path 1>
- <path 2>

Strict out of scope:
- <explicit non-goal 1>
- <explicit non-goal 2>
- no unrelated files
- no private customer data

Validation:
- <command 1>
- <command 2>

PR requirements:
Open one narrow PR against main.

PR title:
<expected PR title>

Use standard PR body headings:
- Summary
- Scope
- Changed files
- Out-of-scope confirmation
- Validation performed
- Risks

Include:
Issue: #<issue-number>

Review and merge expectations:
- do not apply labels unless explicitly instructed
- leave human-controlled merge gates intact
- do not merge manually unless explicitly requested

Wrong-workspace guardrails:
- do not use or reference unrelated checkouts
- stop if the active checkout is not Phoenix Office
- stop if repo identity files are missing
- do not carry stale branch or workspace assumptions from prior tasks

Acceptance criteria:
- <observable result 1>
- <observable result 2>
```

## Wrong-Workspace Guardrails

Phoenix operators should assume Codex may still be attached to a stale local workspace from earlier work unless the prompt proves otherwise.

The stale UniFi Optimizer workspace incident showed why every Phoenix handoff should explicitly name the verified checkout and require repo identity checks before editing. A correct Phoenix handoff should tell Codex to stop if it sees unrelated workspace paths, unrelated branch names, missing Phoenix files, or a remote that is not `Phoenix-AI-Platform/phoenix-office`.

Recommended pre-edit checks:

```bash
git remote -v
git status --short --branch
Test-Path .github/workflows/docs_only_auto_merge.yml
Test-Path src/phoenix_office
```

When a task does not involve workflows, replace the workflow path with another expected repo file. The point is to verify the active checkout, not to make workflow files a universal dependency.

## Safety Notes

The handoff must not include secrets, private customer data, raw credentials, generated business output, or DOCX/proposal content.

The handoff must not authorize Codex to:

- execute orchestration plans
- run `orchestration execute`, `run`, `apply`, `approve`, or `reject`
- mutate approvals, rejections, plans, or reviews
- invoke Codex from GitHub Actions
- call Codex APIs
- create or remove labels
- post PR comments or status comments
- update branches except the task branch explicitly used for the PR
- add auto-approval or auto-merge behavior
- change proposal generation or DOCX rendering behavior
- infer pricing, scope, notes, item descriptions, or customer data
- enqueue, schedule, retry, persist, or run background workers
- add API, MCP, server, worker, or background behavior

A human may still decide to start Codex manually after reviewing the handoff. That decision is outside automation and remains a human-controlled trigger.

## Review And Merge Expectations

The resulting PR should link the issue, use the required body headings, and report validation honestly.

Docs-only PRs may be eligible for existing human-controlled docs-only processes only if they satisfy those separate gates. Execution-adjacent, runtime, proposal, DOCX, schema/model, API/MCP/server/worker/background, and uncertain-risk changes remain human-review and human-merge only unless a later reviewed policy explicitly changes that boundary.

## Non-Goals

This handoff note does not add or authorize:

- workflow behavior changes
- CI behavior changes
- issue-to-Codex automation
- Codex invocation from GitHub Actions
- Codex API calls
- auto-approval behavior
- auto-merge eligibility changes
- label creation, removal, or mutation behavior
- PR comments or status comments
- branch update behavior
- artifacts
- runtime code changes
- CLI behavior changes
- proposal generation changes
- DOCX rendering changes
- tests or fixtures
- orchestration execution, approval, rejection, apply, run, queueing, scheduling, retries, persistence, API behavior, MCP behavior, server behavior, worker behavior, or background behavior
