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

## Atomic Commit

The operation must durably commit one indivisible unit containing:

- the immutable claim record
- the sequence-zero audit event
- the initial snapshot
- uniqueness entries for `attempt_id`, `authorization_id`, and `authorization_fingerprint`

All four visible parts must become durable together or not at all. Interrupted, failed, or crashed creation must expose no partial claim, event, snapshot, or uniqueness entry.

Success may be returned only after the complete unit is durably committed.

## Conflict Rules

Only one concurrent create may win.

Existing identical data is still a conflict. No overwrite, reset, replacement, retry reuse, or idempotent success is allowed.

When multiple uniqueness keys conflict, deterministic precedence is:

1. `attempt_id`
2. `authorization_id`
3. `authorization_fingerprint`

The implementation must report the first conflicting key in that order and must not vary that precedence by backend, timing, or storage layout.

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

## Trust Boundary

Only trusted Phoenix gate/storage code may create or read the durable unit. The worker process receives no storage write capability.

## Non-Goals

This document does not add storage implementation, schema migration, database code, filesystem code, lock code, adapter code, claim creation implementation, event append code, snapshot mutation code, authorization-consumption implementation, CLI code, invocation behavior, GitHub/network access, retries, scheduling, background work, proposal/DOCX changes, private data, generated artifacts, or project-state updates.
