# Core 0.2 Artifact Ledger Reference

## Status

Executable reference semantics. This module is not a Core 0.2 Host adapter,
does not make Core 0.2 claimable, and does not implement an object store,
malware scanner, retention worker, or user-facing download URL.

The reference implementation is
[`src/lap_protocol/artifact_ledger.py`](../src/lap_protocol/artifact_ledger.py).
Its executable evidence is
[`tests/test_core_02_artifact_ledger.py`](../tests/test_core_02_artifact_ledger.py).

## Scope

`ArtifactLedger` is a deterministic state machine for one Host-issued
`tenant_id` and `run_id` scope. It implements the Core 0.2 rules that make a
deliverable reliable instead of an Agent output side field:

- an Offer has one immutable ID, name, MIME type, exact byte size, lowercase
  SHA-256, profile-resolvable source reference, delivery policy, and semantic
  role;
- private filesystem paths and path-like artifact names are rejected rather
  than becoming transport-visible identifiers;
- a repeated identical Offer returns the prior record; reusing its ID with any
  changed immutable metadata is `LAP-109`;
- a Host policy admits or rejects MIME types, delivery kinds/scopes, per-item
  bytes, and count before a receipt can exist;
- a commit validates the exact offered byte count and SHA-256, then creates an
  opaque receipt and canonical `lap://artifact/<receipt>` reference;
- committing the same already validated Artifact is idempotent; changed bytes
  receive no receipt;
- a successful `run.result` names receipt IDs only. Every required offered
  Artifact must have one receipt, while optional Artifacts do not block
  success;
- failed, cancelled, timed-out, and indeterminate results may still name
  committed preview or error-report receipts, but receive the same opaque-ID,
  existence, duplicate, and Run-scope validation without the success gate;
- receipt selection is restricted to the ledger's Host-issued Run scope and
  never returns byte content, source references, or private storage paths.

## Required Host Transaction

The reference ledger intentionally does not retain bytes. A production Host
must make the following operation atomic from its durable storage perspective:

```text
receive validated artifact.offer
        |
        v
copy/scan/hash bytes in Host-owned scoped storage
        |
        v
persist bytes + immutable receipt + audit record
        |
        v
emit artifact.committed from a durable outbox
        |
        v
accept run.result only after required receipt records exist
```

An in-memory `commit()` return is not proof that an object store write
survived a crash. A Host must not expose a download capability or acknowledge
a successful terminal state until its object record, receipt record, and
terminal transition satisfy its own durable transaction/outbox guarantees.

## Failure Rules

| Condition | Reference outcome | Host follow-up |
|---|---|---|
| Offered bytes have a different size or SHA-256 | `ArtifactIntegrityError`; no receipt | Discard temporary data and report a typed safe failure. |
| Offer reuses an ID with changed identity | `ArtifactConflictError` / `LAP-109` | Preserve the original immutable record; audit the conflict. |
| MIME, delivery, count, or size policy is denied | policy/quota error; no receipt | Do not copy or expose data. |
| Required receipt missing at success proposal | `ArtifactTerminalError` | Reject success; keep the Run non-successful until a truthful terminal path exists. |
| Receipt belongs to another tenant/Run | safe unknown/out-of-scope rejection | Do not reveal whether the other receipt exists. |

## Evidence Boundary

The reference tests exercise C02-ART-01, C02-ART-02, and C02-ART-03 semantic
transitions. They do not prove object-store durability, scanner behavior,
database rollback, outbox delivery, cross-process concurrency, retention
execution, or cross-tenant access behavior. Those required Host-runtime and
security tests remain pending in
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json).
