# Core 0.2 Run Ledger and Safe Error Reference

## Status

Executable reference semantics. This module is not a Core 0.2 Host adapter,
does not make Core 0.2 claimable, and does not provide durable storage,
distributed locking, redaction, provider reconciliation, or an outbox.

The reference implementation is
[`src/lap_protocol/run_ledger.py`](../src/lap_protocol/run_ledger.py). Its
executable evidence is
[`tests/test_core_02_run_ledger.py`](../tests/test_core_02_run_ledger.py).

## Scope

`RunLedger` applies the Host-owned portion of one Core 0.2 Run identified by a
Host-issued tenant and Run scope. It makes these portable facts executable:

- `run.start`, `run.accepted`, structured input, reconciliation, and cancel
  request transitions accept only their declared prior states;
- every accepted event has an opaque event ID plus a deterministic event-type
  and payload fingerprint; an exact retry returns the prior outcome, while a
  reused ID with changed data is `LAP-109`;
- a `run.result` is parsed against the existing Core terminal shape, including
  successful-output, non-success-error, finite JSON, and unique receipt-ID
  requirements;
- when a same-scope `ArtifactLedger` is supplied, a successful result must
  pass required-receipt gating before a terminal record exists. Other terminal
  results validate each referenced receipt without requiring every deliverable;
- the first legal terminal event is immutable. A concurrent cancellation
  confirmation and result produce one terminal record; the later event is
  retained as a deduplicated anomaly and cannot rewrite history;
- a Host `run.result.ack` is idempotent and references that immutable terminal
  ledger record;
- `indeterminate` is terminal and its `retry_permitted` value is always false
  for the original Run, even if untrusted error metadata contains a retry hint.

`SafeError` validates only Core object shape: code, bounded text, optional
constraint/correlation/responsibility fields, and a bounded recovery action.
It deliberately cannot infer whether arbitrary text contains a secret. The
Host must redact before it creates this object or writes a diagnostic record.

## Required Host Transaction

The reference is thread-safe only inside one process. A production Host must
make the terminal operation atomic from its durable-storage perspective:

```text
validate authenticated envelope + accepted stream position
        |
        v
validate Artifact receipt set / Profile completion conditions
        |
        v
persist transition + immutable terminal record + audit entry
        |
        v
persist run.result.ack in a durable outbox
        |
        v
publish acknowledgement and user-visible terminal state
```

Memory locking cannot resolve a database failure, two Host processes, provider
ambiguity, or an acknowledgement lost after commit. Recovery restores only a
durably proven terminal record; if an external Effect remains unproven past its
policy deadline, the original Run records `indeterminate` and a Profile-owned
reconciliation operation supplies later evidence without rewriting history.

## Failure Rules

| Condition | Reference outcome | Host follow-up |
|---|---|---|
| `run.result` omits output for success or error for non-success | `RunValidationError`; no terminal record | Reject the proposal and keep the Run active or choose a truthful Host terminal path. |
| Required Artifact lacks a receipt | Artifact terminal rejection; no terminal record | Do not report success or expose a partial deliverable. |
| Event ID is replayed with changed type or payload | `RunConflictError` / `LAP-109` | Preserve original event evidence and audit the conflict. |
| Result and cancellation race | first legal terminal wins; later event is a recorded anomaly | Persist the winner once; do not overwrite it during recovery. |
| External outcome cannot be proven | immutable `indeterminate`; `retry_permitted` is false | Reconcile through a negotiated Profile; never blindly repeat the effect. |
| Error text is unredacted | outside reference detection | Redact before durable audit, telemetry, or user-visible diagnostics. |

## Evidence Boundary

The reference tests exercise C02-RUN-01, C02-RUN-02, and C02-ERR-01 semantic
transitions. They do not prove database durability, outbox delivery, process
kill recovery, HA fencing, secret redaction, external Effect behavior, or
cross-process concurrency. Those required Host-runtime and Profile tests
remain pending in
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json).
