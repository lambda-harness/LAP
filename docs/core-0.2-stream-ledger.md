# Core 0.2 Stream Ledger Reference

## Status

Executable reference semantics. This module is not a Core 0.2 Host adapter,
does not make Core 0.2 claimable, and does not replace a Host's durable
database transaction.

The reference implementation is
[`src/lap_protocol/stream_ledger.py`](../src/lap_protocol/stream_ledger.py).
Its executable evidence is
[`tests/test_core_02_stream_ledger.py`](../tests/test_core_02_stream_ledger.py).

## Scope

`StreamLedger` is deliberately one stream's deterministic state machine. It
implements the Core 0.2 rules that are easy to get subtly wrong when each Host
reinvents them:

- a writer obtains epoch 1, then each successor obtains exactly the next
  epoch; an older writer is fenced from appending;
- each epoch starts at sequence 1 and accepts only its next contiguous
  position;
- an exact same-position resend returns the prior idempotent outcome, while a
  different event ID or body at that position is a conflict;
- an ACK advances only through an already applied contiguous sequence;
- replay is paged and bounded; when a required replay body was evicted, it
  explicitly reports unavailability rather than silently omitting it;
- replay body retention and duplicate detection are separate. A compact
  identity record remains after an old body is evicted, so an old conflicting
  resend cannot be mistaken for a duplicate;
- `export_state()` and `from_state()` preserve epoch, applied/ACK waterlines,
  retained replay bodies, and duplicate identities across a restart.

The input payload is copied through deterministic JSON serialization solely
for reference duplicate comparison. It is not the RFC 8785 release or
capability canonicalization algorithm defined by Core 0.2.

## Required Host Transaction

The reference object is in-memory. A production Host must make each critical
transition durable before it emits an acknowledgment or performs a dependent
business transition:

```text
validate authenticated peer and Core schema
        |
        v
acquire epoch / apply frame / update run state
        |
        v
persist ledger checkpoint + business transition atomically
        |
        v
write durable outbound stream.ack intent
        |
        v
send stream.ack; retry delivery from the durable outbox when needed
```

Returning from `acknowledge()` only records a reference-state waterline. It is
not a persistence guarantee. A Host must also protect the transaction with its
own tenant scope, authenticated peer binding, lease ownership, retention
policy, durable storage, and outbox/failover rules.

## Recovery Rules

| Condition | Reference outcome | Host follow-up |
|---|---|---|
| Same frame is received after its ACK was lost | `duplicate`; no second state transition | Re-send the already durable ACK or replay response. |
| Sequence jumps over an unapplied frame | `SequenceGapError`; no state mutation | Request bounded replay from the exact waterline. |
| Requested replay predates retained body data | `ReplayUnavailableError`; no fabricated event | Resume only with a provable snapshot or end with a typed truthful outcome. |
| Former writer emits after a newer epoch | `StaleEpochError`; no state mutation | Audit the fenced producer and keep the newer lease authoritative. |
| Checkpoint fails validation after restart | `CheckpointError`; no guessed state | Stop/resume through a Host reconciliation path, never silently recreate state. |

## Evidence Boundary

The reference tests exercise C02-STREAM-01, C02-STREAM-02,
C02-STREAM-03, and C02-RESUME-01 semantic transitions. They do not yet inject
Host storage loss, process kill, network half-frames, cross-process lease
races, tenant replay attempts, or a second Host. Those required Host-runtime
tests remain pending in
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json).
