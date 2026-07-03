# Supervised Codex Pilot Authorization Runbook

## Purpose

This runbook defines the first human authorization path for a one-time, documentation-only supervised Codex invocation pilot.

The pilot chain is intentionally staged:

1. a reviewed `CodexHandoffPackage`
2. a completed supervised-pilot evidence package
3. a successful `dev codex-pilot-preflight` result
4. an explicit human authorization decision
5. one supervised docs-only Codex run
6. one branch
7. one pull request
8. stop for assistant architecture review

The first three inputs establish eligibility for human authorization review only. They do not authorize invocation, branch creation, pull-request creation, approval, merge, workflow dispatch, proposal generation, DOCX generation, orchestration execution, or background work.

## Authorization Packet

Before a human may authorize the pilot, the operator must assemble a bounded authorization packet. The packet must be reviewed without including credentials, tokens, raw command output, private customer data, usernames, home directories, machine paths, config contents, raw evidence bodies, or prompt secrets.

The authorization packet must confirm:

- repository: `Phoenix-AI-Platform/phoenix-office`
- exact `main` commit SHA used as the pilot base
- exact committed handoff-package path
- handoff ID from the committed handoff package
- exact committed evidence-package path
- matching handoff ID from the evidence package
- exact successful `python -m phoenix_office.cli dev codex-pilot-preflight <handoff.json> <evidence.json>` command
- sanitized preflight result showing eligibility for human authorization review
- one explicitly named documentation-only objective
- no more than three allowed Markdown files
- allowed files limited to `docs/process/**/*.md` and `docs/development/**/*.md`
- exact expected PR title
- exact branch name
- exact validation commands
- explicit per-run budget or usage ceiling and proof that it is enforceable
- explicit timeout and operator cancellation procedure
- confirmed Codex authentication and runner access
- confirmed branch-creation permission
- confirmed pull-request creation permission
- duplicate active-PR check result
- branch-collision check result
- confirmation that Codex cannot approve or merge
- confirmation that final CI remains mandatory on the created PR head
- confirmation that separate assistant architecture review remains mandatory
- explicit human authorization decision
- authorizer role

The package must not rely on issue text as executable authority. If any value differs from the reviewed handoff package, evidence package, preflight output, branch name, base SHA, or expected PR title, the pilot is blocked.

## One-Time Boundary

A human-authorized pilot is limited to one invocation attempt. Authorization expires after that attempt or after any reviewed input changes.

The pilot boundary is:

- human-triggered only
- one already-reviewed handoff package
- one completed evidence package
- one successful composite preflight for the same handoff ID
- documentation-only
- no more than three Markdown files
- allowed paths limited to `docs/process/**/*.md` and `docs/development/**/*.md`
- fixed repository
- fixed base commit
- fixed branch name
- fixed expected PR title
- no issue discovery
- no autonomous task selection
- no retries
- no automatic restart
- no scheduling
- no background execution
- no approval or merge by Codex
- stop immediately after opening one PR

The pilot must not touch runtime code, tests, workflows, schemas, package files, fixtures, examples, JSON data, templates, proposal behavior, DOCX behavior, orchestration behavior, API behavior, MCP behavior, server behavior, worker behavior, background behavior, or customer data.

## Stop Conditions

The pilot must stop before invocation when:

- the composite preflight exits nonzero
- the preflight result is stale
- any package path, handoff ID, repository, base SHA, branch, expected PR title, allowed file, or validation command differs from the reviewed authorization packet
- the budget or usage ceiling cannot be enforced
- the timeout cannot be enforced
- operator cancellation is unavailable or unclear
- Codex authentication or runner access is uncertain
- branch creation permission is uncertain
- PR creation permission is uncertain
- a duplicate active PR exists
- the target branch already exists
- Codex requests broader scope
- Codex requests additional files
- any non-Markdown file would change
- any secret, private customer data, environment value, machine path, username, home directory, or config content appears
- the task attempts network or GitHub actions outside the authorized branch and PR creation boundary

The pilot must stop during or after invocation when:

- the run exceeds budget or usage limits
- the run exceeds timeout
- the operator cancels the run
- Codex attempts approval, merge, workflow dispatch, retry, scheduling, or background behavior
- Codex changes unexpected files
- Codex changes any non-Markdown file
- Codex opens more than one branch or PR

Stop means no retry, no follow-up automation, no approval, no merge, no comments, no labels, no workflow dispatch, and no background continuation.

## Decision States

The pilot authorization lifecycle uses these states:

- `not_evaluated`: required inputs have not been reviewed.
- `blocked`: at least one required input, control, permission, boundary, or safety condition fails.
- `eligible_for_human_authorization`: handoff, evidence, and composite preflight support human review, but no invocation is authorized.
- `human_authorized_for_one_run`: a human authorizer approves exactly one invocation attempt for the reviewed packet.
- `invocation_started`: the authorized supervised run has begun.
- `pr_opened_and_stopped`: Codex opened the authorized PR and stopped.
- `aborted`: the run stopped before a valid PR was opened.
- `completed_pending_review`: the PR is open, Codex has stopped, and final CI plus assistant architecture review remain pending or under review.

Only explicit human authorization can enter `human_authorized_for_one_run`. That state authorizes one attempt only and expires after the attempt or any reviewed input change.

## Execution Procedure

1. Verify the working repository is `Phoenix-AI-Platform/phoenix-office`.
2. Verify the selected base is the exact reviewed `main` commit SHA.
3. Verify the committed handoff-package path and evidence-package path.
4. Run the exact reviewed composite preflight command.
5. Confirm the sanitized preflight result is successful for the same handoff ID.
6. Confirm duplicate active-PR and branch-collision checks are current.
7. Confirm budget, timeout, cancellation, authentication, runner, branch, and PR controls.
8. Record the human authorization decision and authorizer role.
9. Start exactly one supervised Codex run using the reviewed handoff package.
10. Monitor the run for scope, budget, timeout, cancellation, and stop-condition violations.
11. Allow Codex to create only the authorized branch and one PR.
12. Stop immediately after the PR is opened.
13. Do not approve, merge, comment, label, dispatch workflows, retry, schedule, or continue in the background.

The runbook does not define a current invocation command and does not submit a prompt. The invocation mechanism must come from a separate reviewed pilot implementation and the exact reviewed authorization packet.

## Required Post-Run Evidence

After the run, record bounded evidence without raw prompts, secrets, raw evidence bodies, private customer data, usernames, home directories, config contents, or machine-specific paths.

Required post-run evidence:

- invocation start status
- invocation end status
- bounded usage or cost result
- timeout status
- cancellation status
- exact created branch
- exact created PR
- changed filenames
- confirmation that no unexpected files changed
- final CI status for the exact PR head
- assistant architecture review verdict
- confirmation that Codex did not approve or merge
- operator decision on whether a later pilot should be considered

Post-run evidence does not authorize merge. Merge consideration still requires green final CI, separate assistant architecture review, and the normal repository merge authority.

## Non-Goals

This runbook does not add or authorize:

- Codex invocation
- prompt submission
- authentication attempts
- subprocess execution
- network access
- GitHub API access
- issue or PR lookup
- branch creation
- PR creation
- comments
- labels
- approval behavior
- merge behavior
- workflow changes
- evidence collection
- raw logs
- credentials
- secrets
- persistence
- retries
- scheduling
- background work
- proposal behavior
- DOCX behavior
- orchestration execution
