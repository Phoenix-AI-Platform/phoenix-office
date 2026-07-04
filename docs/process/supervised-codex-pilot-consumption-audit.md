# Supervised Codex Pilot Consumption And Audit Contract

## Purpose

This document defines the fail-closed consumption and audit contract required before any future supervised Codex invocation may rely on a `CodexPilotAuthorizationPacket`.

This is a documentation-only design contract. It does not consume authorization, invoke Codex, submit prompts, authenticate, access GitHub, access the network, inspect issues or PRs, create branches, open PRs, write audit records, persist state, schedule work, retry work, approve, merge, or run in the background.

Exact v1 claim, audit event, and attempt snapshot schemas are defined in [Supervised Codex Pilot Claim Record Schemas](supervised-codex-pilot-claim-records.md).

The required future boundary is:

```text
valid one-attempt authorization packet
+ unchanged reviewed inputs
+ successful current preflight
+ no existing consumption record
-> atomically claim exactly one attempt
-> record sanitized attempt lifecycle
-> never reuse the authorization
```

## Decision Boundaries

The following states are separate and must never imply each other without an explicit validated transition:

- Structurally valid authorization packet: the packet is well formed and safe to inspect.
- Operationally unconsumed authorization: no durable claim exists for the authorization identity or fingerprint.
- Atomically consumed authorization: a durable exclusive claim has been created.
- Invocation lifecycle state: the attempt has advanced through bounded runtime states.
- Post-run review state: final CI and assistant architecture review are known or pending.
- Merge authority: a human or approved routine merge authority decides whether to merge after review.

Successful packet inspection does not imply operationally unconsumed authorization. Successful claim creation does not imply invocation success. Successful invocation does not imply review approval. Successful audit does not imply merge authority.

## Immutable Identity

A future consumption record must bind at minimum:

- authorization schema version
- authorization ID
- handoff ID
- repository
- pilot kind
- base commit SHA
- branch name
- expected PR title
- objective identity
- allowed paths
- validation commands
- budget metric and ceiling
- timeout
- every required control-reference identifier
- `one_invocation_only`
- `retry_authorized`
- `background_execution_authorized`

The future implementation must compute a deterministic canonical fingerprint over the validated safe authorization fields.

Fingerprint schema version: `phoenix-codex-authorization-fingerprint.v1`.

The v1 canonical payload must include exactly these fields from the structurally valid and binding-valid authorization packet:

- `schema_version`
- `authorization_id`
- `repository`
- `pilot_kind`
- `decision_state`
- `authorizer_role`
- `base_commit_sha`
- `handoff_path`
- `evidence_path`
- `handoff_id`
- `objective`
- `allowed_paths`
- `expected_pr_title`
- `branch_name`
- `validation_commands`
- `budget_metric`
- `budget_ceiling`
- `budget_enforcement_ref`
- `timeout_seconds`
- `cancellation_ref`
- `authentication_runner_ref`
- `branch_permission_ref`
- `pr_permission_ref`
- `duplicate_pr_check_ref`
- `branch_collision_check_ref`
- `codex_no_approve_merge_ref`
- `final_ci_required`
- `assistant_review_required`
- `worker_may_approve`
- `worker_may_merge`
- `one_invocation_only`
- `retry_authorized`
- `background_execution_authorized`

List ordering is preserved exactly as validated for `allowed_paths` and `validation_commands`; the implementation must not sort those list values during fingerprinting. Object keys are serialized with sorted keys. Canonical serialization is UTF-8 JSON using no insignificant whitespace and fixed separators equivalent to `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

Before serialization, every string in the payload must already be validated as safe printable text by the authorization inspector. Non-ASCII, control characters, Unicode normalization ambiguity, invalid surrogates, or implementation-dependent Unicode handling must fail closed before fingerprinting rather than being normalized silently.

The digest input is:

```text
phoenix-codex-authorization-fingerprint.v1\n
```

followed by the canonical UTF-8 JSON bytes. The digest algorithm is SHA-256, and the representation is lowercase 64-character hexadecimal.

Illustrative canonical payload:

```json
{"allowed_paths":["docs/process/approved-pilot.md"],"assistant_review_required":true,"authentication_runner_ref":"runner-access-reviewed","authorization_id":"pilot-auth-example","authorizer_role":"human_operator","background_execution_authorized":false,"base_commit_sha":"0000000000000000000000000000000000000000","branch_collision_check_ref":"branch-collision-reviewed","branch_name":"codex/approved-pilot","branch_permission_ref":"branch-permission-reviewed","budget_ceiling":50000,"budget_enforcement_ref":"budget-control-reviewed","budget_metric":"tokens","cancellation_ref":"operator-cancel-reviewed","codex_no_approve_merge_ref":"no-approve-merge-reviewed","decision_state":"human_authorized_for_one_run","duplicate_pr_check_ref":"duplicate-pr-reviewed","evidence_path":"reviewed/evidence.json","expected_pr_title":"docs: update approved pilot documentation","final_ci_required":true,"handoff_id":"codex-handoff-example","handoff_path":"reviewed/handoff.json","objective":"Document the approved supervised pilot boundary.","one_invocation_only":true,"pilot_kind":"docs-only-supervised","pr_permission_ref":"pr-permission-reviewed","repository":"Phoenix-AI-Platform/phoenix-office","retry_authorized":false,"schema_version":"codex-pilot-authorization.v1","timeout_seconds":1800,"validation_commands":["PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp","python -m ruff check . --no-cache","git diff --check"],"worker_may_approve":false,"worker_may_merge":false}
```

A future implementation computes:

```text
sha256(
  utf8("phoenix-codex-authorization-fingerprint.v1\n")
  + utf8(canonical_json_payload)
).hexdigest()
```

The read-only inspector command:

```bash
python -m phoenix_office.cli dev codex-pilot-fingerprint <handoff_json> <evidence_json> <authorization_json>
```

reruns the current authorization inspection and reports the deterministic v1 fingerprint only when that inspection succeeds. The command does not create or inspect a consumption claim, persist state, invoke Codex, submit prompts, access GitHub, access the network, create branches, open PRs, approve, merge, or mutate anything.

Successful fingerprinting means only that the reviewed authorization packet has a stable identity under the v1 contract. It does not prove the authorization is unconsumed, claimed, invocation-ready, invoked, externally authorized, enforceable, or sufficient. Claim creation remains a separately reviewed future capability, and the fingerprint is safe identity material rather than invocation authority.

The fingerprint must not include raw prompts, rendered prompts, raw evidence, raw runtime output, credentials, tokens, machine-specific paths, usernames, home directories, environment values, config contents, private customer data, timestamps, hostnames, process IDs, attempt IDs, lifecycle states, audit metadata, or generated attempt metadata.

Any schema, included-field, ordering, serialization, encoding, prefix, digest algorithm, or representation change requires a new fingerprint schema version. A future implementation must never silently change the meaning of `phoenix-codex-authorization-fingerprint.v1`.

If any reviewed authorization field changes, the fingerprint changes and the previous claim cannot authorize the changed packet.

## Atomic Claim

A future implementation must create an exclusive consumption claim before invoking Codex.

Requirements:

- Claim creation is atomic.
- Claim creation is durably confirmed before prompt submission or process launch.
- An existing claim for the same authorization ID always blocks reuse.
- An existing claim for the same authorization fingerprint always blocks reuse.
- No overwrite, reset, retry, or automatic recovery is allowed.
- Aborted, failed, timed-out, cancelled, or crashed attempts still count as the one consumed attempt after claim creation.
- Any second attempt requires a new human authorization packet and a new authorization ID.
- Concurrent processes cannot both claim the same authorization.
- Uncertainty about claim durability blocks invocation.

This document does not select a network service, database, lock service, or filesystem implementation. A later implementation PR must prove storage-neutral atomicity and durability requirements for its chosen mechanism.

Minimum local-filesystem semantics, if a later implementation chooses local files, are:

- exclusive create semantics for the claim record
- durable write confirmation before invocation
- no silent overwrite
- no deletion as a reuse mechanism
- corruption detection for partial or malformed records
- restrictive permissions suitable for the local runner
- sanitized failure categories for operator review
- a separate human-reviewed recovery procedure
- no background cleanup that can make an authorization reusable

Claim creation and audit mutation are privileged gate/audit operations. They must be performed only by a trusted Phoenix gate/audit component, not by the spawned Codex worker process.

The claim/audit store must be outside every Codex-authorized working path and must never be exposed as an allowed resource. The Codex worker must receive no write, delete, rename, truncate, reset, permission-change, or ownership-change capability for claim records, audit records, or their parent store.

Where operating-system identities, sandboxing, filesystem ACLs, or runner isolation are available, the Codex process must run under a principal that cannot mutate the claim/audit store. If technical write isolation cannot be proven before invocation, invocation is blocked.

The worker may receive only the minimum sanitized attempt identity needed for execution. It must not receive storage credentials, mutable record handles, claim paths, audit paths, recovery credentials, or any capability that could alter, delete, reset, approve, merge, or mark its own attempt reusable.

Recovery and lifecycle updates remain privileged gate/audit operations. Detecting unauthorized mutation, disappearance, replacement, ownership change, permission change, truncation, or corruption of claim/audit records blocks reuse and requires human-reviewed recovery.

Codex must not be able to mark its own attempt reviewed, approved, mergeable, completed, recovered, reset, or reusable.

## Lifecycle States

Fixed lifecycle states:

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

Allowed transitions:

- `claim_not_started` -> `claim_created`
- `claim_created` -> `invocation_starting`
- `claim_created` -> `aborted`
- `claim_created` -> `failed`
- `claim_created` -> `cancelled`
- `claim_created` -> `timed_out`
- `invocation_starting` -> `invocation_started`
- `invocation_starting` -> `aborted`
- `invocation_starting` -> `failed`
- `invocation_starting` -> `cancelled`
- `invocation_starting` -> `timed_out`
- `invocation_started` -> `pr_opened_and_stopped`
- `invocation_started` -> `aborted`
- `invocation_started` -> `failed`
- `invocation_started` -> `cancelled`
- `invocation_started` -> `timed_out`
- `pr_opened_and_stopped` -> `completed_pending_review`

Invalid, skipped, duplicate, missing, or out-of-order transitions fail closed. `claim_created` consumes the authorization even if invocation never starts.

## Crash And Recovery

Crash rules:

- Before claim creation: no authorization is consumed; the operator must rerun the current preflight and authorization inspection before any later attempt.
- After claim creation but before invocation: authorization is consumed; recovery may finalize the audit state as `aborted`, `failed`, `cancelled`, or `timed_out`, but must not restart invocation under the same authorization.
- After process launch: authorization is consumed; recovery may inspect bounded state and finalize audit, but must not repeat the invocation.
- After branch creation: authorization is consumed; recovery may record the known branch identity and stop reason, but must not create another branch under the same authorization.
- After PR creation but before local audit completion: authorization is consumed; recovery may record the known PR identity and final state, but must not reopen, duplicate, approve, merge, comment, label, or restart.

Any uncertain state after claim creation blocks reuse. Recovery is allowed only to inspect and finalize sanitized audit state. It may not submit prompts, restart Codex, retry, schedule follow-up work, run in the background, approve, or merge.

## Sanitized Audit Record

A future implementation must record bounded audit evidence for later review.

Minimum fields:

- schema version
- attempt ID
- authorization ID
- authorization fingerprint
- handoff ID
- repository
- base commit SHA
- branch name
- expected PR title
- lifecycle state
- bounded status/result category
- bounded usage result
- timeout result
- cancellation result
- created branch identity when known
- created PR identity when known
- final exact-head CI category when known
- assistant architecture-review verdict when known
- confirmation that Codex did not approve or merge

Timestamps, if later required, are explicit audit metadata only. They must not affect authorization fingerprinting or deterministic validation results.

The audit record must not store:

- raw prompts or rendered prompts
- raw runtime stdout or stderr
- raw evidence bodies
- credentials or tokens
- usernames or home directories
- environment or config contents
- machine-specific absolute paths
- private customer data

Audit writes must be append-only or monotonic. A later state can refine an attempt result, but cannot erase the claim or make the authorization reusable.

## Storage And Permissions

A future implementation must prove:

- exclusive create or compare-and-set semantics
- durable write confirmation
- restrictive file or record permissions
- no silent overwrite
- no deletion as a reuse mechanism
- corruption detection
- sanitized operator-readable failure categories
- a separate human-reviewed recovery procedure
- no background cleanup that can restore authorization reuse

Failure categories must be bounded and stable, such as:

- `claim_already_exists`
- `fingerprint_already_consumed`
- `claim_durability_uncertain`
- `claim_store_unavailable`
- `claim_record_corrupt`
- `invalid_lifecycle_transition`
- `recovery_required`

Failure messages must not include raw prompts, raw evidence, credentials, tokens, usernames, home directories, machine paths, environment values, config contents, private customer data, or raw runtime output.

## Invocation Gate Ordering

A future implementation must use this ordering:

1. Rerun authorization packet inspection.
2. Verify all reviewed inputs are unchanged.
3. Verify the authorization has no existing claim.
4. Atomically create and durably confirm the claim.
5. Record `claim_created`.
6. Only then permit one invocation attempt.
7. Record every later state monotonically.
8. Stop after one PR or any abort condition.

No prompt may be submitted and no Codex process may start before step 5 succeeds.

If any step is missing, stale, uncertain, conflicting, duplicated, or out of order, the implementation must fail closed before invocation.

## Responsibilities

Human operator:

- creates or approves a new authorization packet
- confirms reviewed inputs and external controls
- confirms budget, timeout, cancellation, and runner availability
- decides whether a new authorization is required after any consumed attempt

Future runner:

- may consume an already-reviewed authorization only through the reviewed claim mechanism
- must never create, broaden, delete, reset, or reuse authorization
- must never approve or merge
- must stop after one PR or any abort condition

Assistant reviewer:

- reviews scope, changed files, final CI, audit categories, and architecture boundaries
- verifies Codex did not approve or merge
- does not treat invocation or audit success as merge authority

Merge authority:

- remains separate from authorization, consumption, invocation, and audit
- requires final CI and assistant architecture review before any merge decision

## Non-Goals

This contract does not add or authorize:

- Python changes
- tests
- CLI behavior beyond the read-only fingerprint inspector
- subprocess calls
- Codex invocation
- prompt submission
- authentication
- network access
- GitHub access
- issue or PR lookup
- branch creation
- PR creation
- comments
- labels
- approval behavior
- merge automation
- workflow changes
- persistence implementation
- filesystem writes
- database changes
- lock implementation
- audit-log implementation
- retries
- scheduling
- background work
- proposal behavior
- DOCX behavior
- orchestration execution
- generated artifacts
- private customer data
