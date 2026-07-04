# Supervised Codex Pilot Initial Claim Storage Contract

## Purpose

This document defines the v1 durable storage contract for exactly one already-valid initial claim bundle. It is documentation only. It does not implement storage, schemas, migrations, locks, adapters, CLI behavior, invocation behavior, or project-state updates.

The required future boundary is:

```text
validated initial bundle
→ one atomic durable commit
→ claim + sequence-zero event + snapshot + uniqueness entries visible together
```

## Required Operation

A future trusted Phoenix gate/storage component must expose a backend-neutral `create_initial_claim_bundle(bundle)` operation.

Inputs:

- `bundle` must be the successful output of `compose_codex_pilot_initial_claim_bundle(...)`
- `bundle` must be fully revalidated immediately before any mutation

The operation must treat the bundle as already complete and must not repair, rewrite, enrich, normalize, or partially accept it.

## Trusted Authorization Context

The bundle alone is not sufficient to authorize create or read. The gate/storage component must also hold the exact inspected `CodexPilotAuthorizationPacket` object that produced the bundle, or an immutable reviewed authorization snapshot that is provably the same packet and is looked up from a trusted Phoenix authorization store by `authorization_id`.

Before mutation, the operation must revalidate that exact authorization context and bind it to the bundle. The create path must recompute and compare the authorization fingerprint and objective digest from that context, and must compare every projected field in the bundle against that same context. The read path must use the same trusted authorization context for verification and must not reconstruct authorization from the claim, from the snapshot, or from fingerprint equality alone.

If the trusted authorization context is missing, mutable, or cannot be proven identical to the inspected packet that produced the bundle, the operation fails closed.

## Atomic Commit

The operation must durably commit one indivisible unit containing:

- the immutable claim record
- the sequence-zero audit event
- the initial snapshot
- uniqueness entries for `attempt_id`, `authorization_id`, and `authorization_fingerprint`

All four visible parts must become durable together or not at all. Interrupted, failed, or crashed creation must expose no partial claim, event, snapshot, or uniqueness entry.

Success may be returned only after the complete unit is durably committed.

There is one linearization point for the full unit: the authoritative commit or publish of the complete committed manifest/catalog for the bundle. All validation, uniqueness checks, staging, and publication must observe one consistent prepublication snapshot. Readers must ignore temporary, staged, or uncommitted state that is not referenced by the authoritative committed unit.

## Conflict Rules

Only one concurrent create may win.

Existing identical data is still a conflict. No overwrite, reset, replacement, retry reuse, or idempotent success is allowed.

When multiple uniqueness keys conflict, deterministic precedence is:

1. `attempt_id`
2. `authorization_id`
3. `authorization_fingerprint`

The implementation must report the first conflicting key in that order and must not vary that precedence by backend, timing, or storage layout.

For a transactional database backend, the linearization point is one durable serializable transaction that covers validation, conflict checks, staging, and publication, and does not rely on backend-dependent unique-error ordering for conflict classification.

For an atomic-filesystem backend, the linearization point is one exclusive create or compare-and-set critical section that stages every record privately, publishes one authoritative committed manifest/catalog atomically, and ensures every conflict is evaluated against the same prepublication snapshot. Temporary files, partial directories, or crash remnants are non-authoritative and must never be treated as success.

## Canonical Stored Bytes

Any stored record bytes written by the durable unit must use exact canonical JSON encoding:

- UTF-8
- sorted keys
- compact separators
- `ensure_ascii=False`
- no BOM
- no trailing newline
- no wrapper fields inside contract records

Exact Unicode / ASCII rule:

- strings are stored as JSON strings
- non-ASCII code points are preserved as UTF-8 bytes
- no Unicode normalization is permitted during storage
- no ASCII escape forcing is permitted beyond normal JSON escaping of required control characters

The canonical encoding requirement applies to every contract record stored as part of the unit. The storage layer must not add metadata wrappers around the claim, event, snapshot, or uniqueness records.

## Uniqueness Entry Shape

The durable unit contains exactly three logical uniqueness entries:

- `attempt_id` maps to the bundle's immutable claim attempt identity and the authoritative committed unit locator.
- `authorization_id` maps to the exact trusted authorization context's `authorization_id` and the same authoritative committed unit locator.
- `authorization_fingerprint` maps to the exact trusted authorization context's recomputed fingerprint and the same authoritative committed unit locator.

No alias keys, secondary indexes, wrapper records, or extra payload fields are permitted inside the contract. The uniqueness entries exist only to make the complete committed unit discoverable and to prove the one-winner conflict boundary.

## Backend-Equivalent Requirements

### Transactional Database Backend

A transactional database implementation must:

- use one atomic transaction for the full unit
- ensure every visible record and uniqueness entry becomes durable together
- reject any partial flush, delayed visibility split, or per-record commit
- preserve deterministic conflict precedence
- fail closed if commit durability cannot be proven
- avoid any repair or retry path that can turn a conflict into success

### Atomic Filesystem Backend

An atomic-filesystem implementation must:

- write the full unit using atomic publish semantics
- ensure readers never observe a mix of old and new unit members
- ensure uniqueness entries and records are not published separately
- reject any partial file, directory, or rename sequence that could expose a partial unit
- preserve deterministic conflict precedence
- fail closed if atomic durability cannot be proven
- avoid any cleanup path that can make a failed create appear successful

If the backend cannot provide a single authoritative publication point plus a consistent conflict snapshot for all three uniqueness keys, it is non-conforming.

## Read Operation

A future trusted Phoenix gate/storage component must also expose a read operation that loads the complete committed unit and revalidates all stored data.

The read operation must:

- load the claim record, sequence-zero event, snapshot, and uniqueness entries together
- verify the exact committed sequence-zero history
- verify all record bindings, digests, identities, and uniqueness entries
- fail closed on missing, duplicate, mismatched, stale, corrupt, or uncertain data
- never repair storage
- never overwrite storage
- never synthesize missing data

If any part of the committed unit is missing or inconsistent, the read operation must fail and must not attempt self-healing.

## Sanitized Result Categories

Create and read operations must return only bounded sanitized categories and must not echo record values.

Create operation categories:

- `created`
- `bundle_invalid`
- `authorization_context_invalid`
- `bundle_binding_mismatch`
- `attempt_id_conflict`
- `authorization_id_conflict`
- `authorization_fingerprint_conflict`
- `claim_store_unavailable`
- `claim_durability_uncertain`
- `commit_incomplete`
- `claim_record_corrupt`
- `audit_event_corrupt`
- `snapshot_corrupt`

Read operation categories:

- `read_success`
- `authorization_context_invalid`
- `bundle_binding_mismatch`
- `missing_commit`
- `commit_incomplete`
- `claim_record_corrupt`
- `audit_event_corrupt`
- `snapshot_corrupt`
- `uniqueness_entry_corrupt`
- `digest_mismatch`
- `identity_mismatch`
- `history_mismatch`
- `claim_store_unavailable`
- `claim_durability_uncertain`

## Trust Boundary

Only trusted Phoenix gate/storage code may create or read the durable unit. The worker process receives no storage write capability.

## Non-Goals

This document does not add storage implementation, schema migration, database code, filesystem code, lock code, adapter code, claim creation implementation, event append code, snapshot mutation code, authorization-consumption implementation, CLI code, invocation behavior, GitHub/network access, retries, scheduling, background work, proposal/DOCX changes, private data, generated artifacts, or project-state updates.
