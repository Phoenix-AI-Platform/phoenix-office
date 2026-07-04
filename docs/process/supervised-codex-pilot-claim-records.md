# Supervised Codex Pilot Claim Record Schemas

## Purpose

This document defines the exact v1 record schemas for a future supervised Codex pilot claim and audit layer. It is documentation only. It does not create or inspect claims, persist state, write files, invoke Codex, submit prompts, authenticate, access GitHub, create branches, open PRs, approve, merge, retry, schedule, or run background work.

The schemas preserve separate meanings for authorization identity, atomic claim creation, invocation lifecycle, post-run review, and merge authority. A valid record never means Codex may run, approve, merge, or reuse an authorization unless a later reviewed implementation explicitly adds that behavior behind the required gates.

The repository includes pure in-memory validation helpers for candidate `codex-pilot-claim.v1` records and their binding to an already-inspected authorization packet. It also includes a pure deterministic initial-claim bundle composer that creates the claim record, sequence-zero audit event, and derived snapshot in memory only. Those helpers do not read files, write files, create claims, append events, inspect storage, invoke Codex, or consume authorization. The durable `create_initial_claim_bundle(bundle)` storage contract is defined separately in [Supervised Codex Pilot Initial Claim Storage Contract](supervised-codex-pilot-storage.md).

## Schema Versions

The exact v1 schema versions are:

- `codex-pilot-claim.v1`
- `codex-pilot-audit-event.v1`
- `codex-pilot-attempt-snapshot.v1`

Each record root is a JSON object with exactly the fields defined for its schema. Missing fields, unknown fields, wrong JSON types, invalid enum values, duplicate list values, unsafe strings, or non-canonical ordering fail closed. Any schema, field, type, enum, transition, validation, ordering, or digest change requires a new schema version.

## Shared Safe Types

All string fields must be printable ASCII, single-line, trimmed, bounded, and free of control characters. Unicode normalization ambiguity is rejected rather than normalized. Strings must not contain URLs, absolute paths, home-directory markers, drive markers, `Users`, `AppData`, usernames, hostnames, credentials, tokens, `sk-` values, passwords, secrets, environment assignments, config contents, raw prompts, raw evidence, runtime stdout/stderr, private customer data, or arbitrary free-form error text.

Opaque identifiers allow only alphanumeric characters plus `-`, `_`, and internal `.`. They reject `.`, `..`, `/`, `\`, `:`, `=`, URL markers, path markers, credential-like content, and values longer than 80 characters.

Repository-relative Markdown paths must be unique strings under `docs/process/**/*.md` or `docs/development/**/*.md`, must preserve the exact validated authorization list order, must not include `docs/development/project_state.md`, and must reject traversal, absolute paths, backslashes, URLs, workflow paths, source paths, tests, fixtures, examples, JSON, templates, DOCX, package files, proposal paths, customer-data paths, API/MCP/server/worker paths, and generated outputs.

Repository-relative JSON paths must be safe `.json` paths with no traversal, absolute path, drive marker, repeated separator, URL, backslash, credential-like content, machine-specific content, or ambiguous path segment.

Integers must be JSON integers, not booleans. Booleans must be actual JSON booleans. Lists must use deterministic ordering specified by the field definition and reject duplicates unless explicitly allowed. Diagnostics must use fixed categories and must not echo unsafe input values.

## Atomic Claim Record

Schema version: `codex-pilot-claim.v1`.

The claim record is immutable. It binds an authorization fingerprint to exactly one attempt and starts in lifecycle state `claim_created`. Atomic claim creation must durably create both the immutable claim record and audit event sequence `0` for `claim_not_started -> claim_created` as one indivisible operation. No valid claimed attempt may exist without both records.

The claim stores a safe authorization identity projection directly. That projection is not a second identity system. It is a review aid that must be proven against the existing `phoenix-codex-authorization-fingerprint.v1` identity before the claim is created.

Required fields and JSON types:

- `schema_version`: string, exactly `codex-pilot-claim.v1`
- `attempt_id`: opaque identifier string created by the trusted Phoenix gate
- `authorization_id`: opaque identifier string
- `authorization_fingerprint_schema_version`: string, exactly `phoenix-codex-authorization-fingerprint.v1`
- `authorization_fingerprint`: lowercase 64-character SHA-256 hex string
- `handoff_id`: opaque identifier string
- `repository`: string, exactly `Phoenix-AI-Platform/phoenix-office`
- `pilot_kind`: string, exactly `docs-only-supervised`
- `base_commit_sha`: lowercase 40-character hex string
- `branch_name`: safe branch string beginning with `codex/`
- `expected_pr_title`: safe one-line string beginning with `docs:`
- `objective_digest_schema_version`: string, exactly `codex-pilot-objective-digest.v1`
- `objective_digest`: lowercase 64-character SHA-256 hex string over the validated safe objective string using prefix `codex-pilot-objective-digest.v1\n`
- `allowed_paths`: one to three unique repository-relative Markdown paths, already validated in lexicographic order by the authorization packet contract
- `validation_commands`: exact ordered list:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp`
  - `python -m ruff check . --no-cache`
  - `git diff --check`
- `budget_metric`: string, exactly `tokens`
- `budget_ceiling`: integer, `1` through `1000000`
- `timeout_seconds`: integer, `60` through `7200`
- `budget_enforcement_ref`: opaque identifier string
- `cancellation_ref`: opaque identifier string
- `authentication_runner_ref`: opaque identifier string
- `branch_permission_ref`: opaque identifier string
- `pr_permission_ref`: opaque identifier string
- `duplicate_pr_check_ref`: opaque identifier string
- `branch_collision_check_ref`: opaque identifier string
- `codex_no_approve_merge_ref`: opaque identifier string
- `final_ci_required`: boolean, exactly `true`
- `assistant_review_required`: boolean, exactly `true`
- `worker_may_approve`: boolean, exactly `false`
- `worker_may_merge`: boolean, exactly `false`
- `one_invocation_only`: boolean, exactly `true`
- `retry_authorized`: boolean, exactly `false`
- `background_execution_authorized`: boolean, exactly `false`
- `initial_lifecycle_state`: string, exactly `claim_created`

The claim record must never contain later lifecycle state, CI state, review state, PR result state, timestamps that affect identity, hostnames, process IDs, runner paths, mutable status fields, raw prompts, rendered prompts, raw evidence, credentials, tokens, environment values, or private customer data.

## Claim Fingerprint Proof

Future claim construction must use this exact proof procedure:

1. Consume the exact in-memory `CodexPilotAuthorizationPacket` object that passed authorization inspection.
2. Validate that object with the shared authorization packet structural validator.
3. Recompute `phoenix-codex-authorization-fingerprint.v1` from that object using the existing fingerprint contract.
4. Require exact equality between the recomputed fingerprint and the claim record `authorization_fingerprint`.
5. Bind every duplicated claim projection field exactly to the same authorization object:
   - `authorization_id`
   - `handoff_id`
   - `repository`
   - `pilot_kind`
   - `base_commit_sha`
   - `branch_name`
   - `expected_pr_title`
   - `allowed_paths`
   - `validation_commands`
   - `budget_metric`
   - `budget_ceiling`
   - `timeout_seconds`
   - every control-reference identifier
   - every required safety boolean
6. Compute `objective_digest` from the same validated safe authorization `objective` string.

The current v1 authorization packet contract requires `allowed_paths` to be lexicographically sorted before fingerprinting. The claim `allowed_paths` list must equal the structurally valid authorization object's list value-for-value and position-for-position. Claim construction and binding validation must not sort, normalize, or rewrite that list. A non-sorted claim list is structurally invalid, and any different sorted list is a claim identity mismatch.

`objective_digest` uses schema `codex-pilot-objective-digest.v1`. The digest input is UTF-8 bytes of:

```text
codex-pilot-objective-digest.v1\n
```

followed by the exact UTF-8 bytes of the validated one-line objective string. The digest algorithm is SHA-256 and the representation is lowercase 64-character hex. No normalization, trimming, or rewriting occurs during digesting; the string must already have passed authorization validation.

Later independent verification requires the original reviewed authorization packet or an equivalent immutable reviewed authorization record to remain available outside the claim store. The claim record intentionally does not copy prompts, raw evidence, secrets, runtime output, or machine data.

## Attempt ID

`attempt_id` is created only by the trusted Phoenix gate during atomic claim creation. Codex must not provide, choose, rewrite, delete, recover, or reuse it.

The format is:

```text
pilot-attempt-[a-z0-9][a-z0-9._-]{11,62}
```

It is bounded to 80 characters including the prefix, safe to emit, and must not contain usernames, hostnames, paths, timestamps that reveal operator or machine details, credentials, tokens, secrets, or customer data. Randomness or time-derived material may be used only as non-authoritative audit metadata for uniqueness. It never changes the authorization fingerprint. A failed, cancelled, timed-out, aborted, crashed, or partially claimed attempt ID is never reused.

## Lifecycle Audit Event

Schema version: `codex-pilot-audit-event.v1`.

An audit event is append-only or monotonic. It binds to the immutable claim and advances the lifecycle by exactly one permitted transition.

The current implementation includes pure deterministic helpers for candidate audit-event validation, digesting, claim/previous-event binding, and initial bundle composition. These helpers inspect explicit in-memory records only. They do not append events, write files, persist state, consume authorization, recover storage, invoke Codex, access GitHub or the network, create branches or PRs, approve, merge, retry, schedule, or run background work.

Required fields:

- `schema_version`: string, exactly `codex-pilot-audit-event.v1`
- `attempt_id`: opaque attempt identifier matching the claim
- `authorization_id`: opaque identifier matching the claim
- `authorization_fingerprint`: lowercase 64-character hex string matching the claim
- `event_sequence`: integer, zero-based, contiguous, no gaps, no duplicates
- `previous_lifecycle_state`: lifecycle enum string
- `next_lifecycle_state`: lifecycle enum string
- `event_category`: exact enum string from the transition matrix
- `result_category`: exact enum string from the transition matrix
- `actor_role`: exact actor role enum string from the transition matrix
- `codex_approved`: boolean, exactly `false`
- `codex_merged`: boolean, exactly `false`
- `previous_event_digest`: `null` for sequence `0`; lowercase 64-character hex string for every later event
- `event_digest`: lowercase 64-character hex string over the event digest payload

Optional fields are allowed only when the transition table permits them:

- `branch_identity`: branch identity string with total length 1 through 100, beginning with `codex/`, and containing only `[A-Za-z0-9._/-]` with no spaces, `..`, `@{`, trailing slash, repeated slash, component beginning with `.`, component ending with `.lock` case-insensitively, secret markers, or machine markers
- `pull_request_identity`: string matching `pr-[1-9][0-9]{0,9}`
- `usage_category`: one of `within_budget`, `budget_exceeded`, `usage_unknown`
- `timeout_category`: one of `timeout_not_reached`, `timeout_reached`, `timeout_unknown`
- `cancellation_category`: one of `operator_cancelled`, `no_cancellation_requested`, `cancellation_unknown`
- `final_ci_category`: one of `passed`, `failed`, `pending`, `unknown`
- `assistant_review_verdict`: one of `approved`, `changes_requested`, `commented`, `pending`, `unknown`
- `recovery_category`: one of `durable_claim_without_invocation`, `runner_crash`, `operator_recovery`, `storage_uncertain`

Unknown fields, missing required fields, optional fields on inapplicable transitions, wrong JSON types, invalid enums, invalid previous-state binding, or unsafe values fail closed.

Exact result categories are:

- `claim_created`
- `started`
- `opened_pr`
- `completed_pending_review`
- `aborted`
- `failed`
- `cancelled`
- `timed_out`

Fields with value `null` are permitted only where the transition matrix explicitly requires `null`. Otherwise an inapplicable field must be absent. Validators reject silently ignored fields.

## Event Chaining

Event chaining is mandatory for v1. The digest schema is `codex-pilot-audit-event-digest.v1`. Every event must include `previous_event_digest` and `event_digest`.

The digest input is UTF-8 bytes of:

```text
codex-pilot-audit-event-digest.v1\n
```

followed by compact canonical JSON for the complete event digest payload with sorted keys, separators equivalent to `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The canonical digest payload contains every event field required for that candidate transition, including `previous_event_digest`, but excludes only the generated `event_digest` field. Unknown, missing, forbidden, unsafe, invalid-transition, or wrong-type payload values fail closed before hashing. The digest algorithm is SHA-256 and the representation is lowercase 64-character hex.

For `event_sequence == 0`, `previous_event_digest` must be JSON `null`. For every later event, `previous_event_digest` must equal the `event_digest` of the immediately preceding event. Missing, duplicate, altered, mismatched, or stale links fail closed.

## Lifecycle States And Transitions

Lifecycle states are fixed:

- `claim_not_started`
- `claim_created`
- `invocation_starting`
- `invocation_started`
- `pr_opened_and_stopped`
- `aborted`
- `failed`
- `cancelled`
- `timed_out`
- `completed_pending_review`

Transition matrix:

| Previous | Next | Event category | Result | Actor | Required optional fields | Required absent optional fields | Terminal | Recovery finalizing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `claim_not_started` | `claim_created` | `claim_created` | `claim_created` | `phoenix_gate` | none | all optional fields | no | no |
| `claim_created` | `invocation_starting` | `invocation_starting` | `started` | `phoenix_gate` | none | all optional fields | no | no |
| `claim_created` | `aborted` | `claim_aborted` | `aborted` | `phoenix_audit` | `recovery_category` | branch, PR, usage, timeout, cancellation, CI, review | yes | yes |
| `claim_created` | `failed` | `claim_failed` | `failed` | `phoenix_audit` | `recovery_category` | branch, PR, usage, timeout, cancellation, CI, review | yes | yes |
| `claim_created` | `cancelled` | `claim_cancelled` | `cancelled` | `phoenix_audit` | `cancellation_category` | branch, PR, usage, timeout, recovery, CI, review | yes | yes |
| `claim_created` | `timed_out` | `claim_timed_out` | `timed_out` | `phoenix_audit` | `timeout_category` | branch, PR, usage, cancellation, recovery, CI, review | yes | yes |
| `invocation_starting` | `invocation_started` | `invocation_started` | `started` | `phoenix_gate` | none | branch, PR, usage, timeout, cancellation, recovery, CI, review | no | no |
| `invocation_starting` | `aborted` | `invocation_start_aborted` | `aborted` | `phoenix_audit` | `recovery_category` | branch, PR, usage, timeout, cancellation, CI, review | yes | yes |
| `invocation_starting` | `failed` | `invocation_start_failed` | `failed` | `phoenix_audit` | `recovery_category` | branch, PR, usage, timeout, cancellation, CI, review | yes | yes |
| `invocation_starting` | `cancelled` | `invocation_start_cancelled` | `cancelled` | `phoenix_audit` | `cancellation_category` | branch, PR, usage, timeout, recovery, CI, review | yes | yes |
| `invocation_starting` | `timed_out` | `invocation_start_timed_out` | `timed_out` | `phoenix_audit` | `timeout_category` | branch, PR, usage, cancellation, recovery, CI, review | yes | yes |
| `invocation_started` | `pr_opened_and_stopped` | `pr_opened_and_stopped` | `opened_pr` | `phoenix_gate` | `branch_identity`, `pull_request_identity`, `usage_category` | timeout, cancellation, recovery, CI, review | no | no |
| `invocation_started` | `aborted` | `invocation_aborted` | `aborted` | `phoenix_audit` | `usage_category`, `recovery_category` | branch, PR, timeout, cancellation, CI, review | yes | yes |
| `invocation_started` | `failed` | `invocation_failed` | `failed` | `phoenix_audit` | `usage_category`, `recovery_category` | branch, PR, timeout, cancellation, CI, review | yes | yes |
| `invocation_started` | `cancelled` | `invocation_cancelled` | `cancelled` | `phoenix_audit` | `usage_category`, `cancellation_category` | branch, PR, timeout, recovery, CI, review | yes | yes |
| `invocation_started` | `timed_out` | `invocation_timed_out` | `timed_out` | `phoenix_audit` | `usage_category`, `timeout_category` | branch, PR, cancellation, recovery, CI, review | yes | yes |
| `pr_opened_and_stopped` | `completed_pending_review` | `completed_pending_review` | `completed_pending_review` | `phoenix_audit` | `branch_identity`, `pull_request_identity`, `final_ci_category`, `assistant_review_verdict` | usage, timeout, cancellation, recovery | yes | no |

`codex_approved:false` and `codex_merged:false` are required on every event, including sequence `0`. The final transition requires `final_ci_category` to be `passed`, `failed`, `pending`, or `unknown`, and `assistant_review_verdict` to be `approved`, `changes_requested`, `commented`, `pending`, or `unknown`. Earlier transitions must omit both fields.

When an optional category is absent by the matrix, the field must be absent rather than present as `null` or a placeholder value.

Matrix shorthand maps to exact field names: branch = `branch_identity`; PR = `pull_request_identity`; usage = `usage_category`; timeout = `timeout_category`; cancellation = `cancellation_category`; recovery = `recovery_category`; CI = `final_ci_category`; review = `assistant_review_verdict`.

For `pr_opened_and_stopped -> completed_pending_review`, `branch_identity` and `pull_request_identity` are required again and must exactly equal the values recorded by the immediately preceding `pr_opened_and_stopped` event. A mismatch fails with `event_binding_mismatch`.

No transition may return to `claim_not_started`, delete a claim, reset an attempt, or make an authorization reusable. Terminal states remain consumed. Recovery may append only a permitted finalizing transition from the current non-terminal state and may never restart invocation.

Duplicate events are rejected in v1. A later idempotency design requires a new schema version. No validator may accept a duplicate append, skip a sequence number, or diverge history under `codex-pilot-audit-event.v1`.

## Attempt Snapshot

Schema version: `codex-pilot-attempt-snapshot.v1`.

The preferred v1 snapshot is derived entirely from the immutable claim plus ordered audit events. A stored snapshot is allowed only as a compare-and-set projection with a verified event sequence. It is never authoritative enough to erase, replace, delete, reset, or make reusable an immutable claim.

The current implementation includes pure deterministic helpers for candidate snapshot validation, ordered event-chain derivation, and candidate-to-derived binding. Standalone snapshot validation checks both field shape and v1 cross-field invariants such as lifecycle state, terminal status, sequence/state compatibility, and contextual branch/PR/CI/review presence. These helpers inspect explicit in-memory records only. They do not persist snapshots, append events, mutate lifecycle state, consume authorization, invoke Codex, access GitHub or the network, create branches or PRs, approve, merge, retry, schedule, or run background work.

Required snapshot fields:

- `schema_version`: string, exactly `codex-pilot-attempt-snapshot.v1`
- `attempt_id`: attempt identifier
- `authorization_id`: authorization identifier
- `authorization_fingerprint`: lowercase 64-character hex string
- `latest_event_sequence`: integer, `0` for a newly claimed attempt with only the required claim-created event
- `latest_event_digest`: lowercase 64-character hex string equal to the final authoritative event's `event_digest`
- `current_lifecycle_state`: lifecycle enum string
- `terminal`: boolean
- `branch_identity`: branch identity using the audit-event branch format, or JSON `null` before a branch is known
- `pull_request_identity`: PR identity using the audit-event PR format, or JSON `null` before a PR is known
- `final_ci_category`: one of `passed`, `failed`, `pending`, `unknown`, or JSON `null` before final CI is known
- `assistant_review_verdict`: one of `approved`, `changes_requested`, `commented`, `pending`, `unknown`, or JSON `null` before assistant review is known
- `codex_approved`: boolean, exactly `false`
- `codex_merged`: boolean, exactly `false`
- `authorization_reusable`: boolean, exactly `false`

Derivation rules:

- Validate the claim first.
- Validate every event against the claim.
- Require the authoritative event stream to already be strictly increasing by `event_sequence`; validators must not sort a supplied stream to hide reordered input.
- Require the first event to be sequence `0` with `claim_not_started -> claim_created`.
- Require no gaps, duplicates, replacement, or reordering.
- Require `latest_event_sequence` and `latest_event_digest` to identify the same final validated event.
- Require every `previous_lifecycle_state` to match the prior derived state.
- Apply transitions exactly from the table.
- Derive current state from the final event.
- Derive terminal status from the transition table.
- Derive `branch_identity` and `pull_request_identity` as JSON `null` until `pr_opened_and_stopped`, then carry forward the exact recorded values through later events.
- Derive `final_ci_category` and `assistant_review_verdict` as JSON `null` until `completed_pending_review`, then equal that event's exact values.
- Reject conflicting duplicates, later rewrites, or contextual values from inapplicable transitions.

For a newly claimed state, `latest_event_sequence` is `0` and `latest_event_digest` equals event sequence `0`'s `event_digest`. If a stored snapshot disagrees with the immutable claim, ordered events, final event sequence, final event digest, or derived contextual fields, the snapshot fails with `snapshot_mismatch`. The claim remains consumed and not reusable.

## Event Ordering And Integrity

`event_sequence` is zero-based and monotonically increasing. Sequence `0` is the mandatory `claim_not_started -> claim_created` event created atomically with the immutable claim. Required behavior:

- no gaps
- no duplicates
- no reordering
- no replacement
- exact event-digest verification
- exact previous-event-digest chaining
- exact previous-state binding
- exact attempt-ID binding
- exact authorization-ID binding
- exact fingerprint binding
- corruption or uncertainty blocks reuse and invocation
- recovery may append only a permitted finalizing transition
- recovery may never submit a prompt, start Codex, create another branch, create another PR, approve, merge, retry, schedule, or run in the background

## Actor Roles

Allowed actor roles:

- `phoenix_gate`
- `phoenix_audit`
- `human_operator`
- `assistant_reviewer`

Codex is not an authorized actor for claim creation, claim replacement, claim deletion, lifecycle recovery, final CI result, assistant review verdict, approval, merge, reuse decisions, record validation, or storage repair.

If a Codex process result is recorded, it is recorded by `phoenix_gate` or `phoenix_audit` as bounded evidence. Codex output is never self-authoritative state.

## Failure Categories

Stable failure categories include:

- `claim_record_invalid`
- `claim_identity_mismatch`
- `claim_already_exists`
- `fingerprint_already_consumed`
- `event_sequence_invalid`
- `event_binding_mismatch`
- `invalid_lifecycle_transition`
- `event_digest_mismatch`
- `snapshot_mismatch`
- `claim_record_corrupt`
- `audit_event_corrupt`
- `claim_store_unavailable`
- `claim_durability_uncertain`
- `recovery_required`
- `unsafe_record_value`
- `unknown_record_fields`

Diagnostics must not echo unsafe values, raw prompts, raw evidence, credentials, tokens, usernames, home directories, hostnames, machine paths, environment values, config contents, runtime output, or private customer data.

## Storage Neutrality

These schemas are storage-neutral. The durable `create_initial_claim_bundle(bundle)` contract and its backend-equivalent requirements are defined in [Supervised Codex Pilot Initial Claim Storage Contract](supervised-codex-pilot-storage.md). A later adapter may use a filesystem, database, service, or other durable store only if it proves:

- exclusive create or compare-and-set semantics
- durable write confirmation
- no silent overwrite
- no deletion as a reuse mechanism
- append-only or monotonic event semantics
- corruption detection
- restrictive permissions
- Codex worker write isolation from claim and audit storage
- sanitized operator-readable failure categories
- human-reviewed recovery
- no background cleanup that can restore authorization reuse

This document does not select or implement a backend.

## Future Implementation Order

The required implementation sequence is:

1. Pure record contracts and validators.
2. Read-only candidate-record inspection.
3. Storage adapter contract tests.
4. Atomic claim creation with no invocation.
5. Lifecycle audit append with no invocation.
6. Recovery inspection.
7. Separately authorized one-run invocation gate.

Each step requires its own reviewed PR. No step may silently add Codex invocation, prompt submission, GitHub access, branch creation, PR creation, approval, merge, retry, scheduling, background work, proposal behavior, DOCX behavior, orchestration execution, generated artifacts, or private customer data.

## Non-Goals

This document does not add Python changes, tests, CLI behavior, persistence, filesystem writes, database changes, locks, atomic create implementation, claim creation, authorization consumption, audit-log writes, recovery mutation, Codex invocation, prompt submission, AI/API calls, subprocess changes, authentication, network access, GitHub access, issue/PR lookup, branch/PR creation, comments, labels, approval, merge automation, workflow changes, retries, scheduling, background work, proposal/DOCX changes, orchestration execution, generated artifacts, private customer data, or project-state updates.
