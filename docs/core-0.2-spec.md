# SPEC: LAP Core 0.2 Reliability Contract

## Status

Design-approved draft. This document is implementation-ready for Core work but
does not authorize the separate commercial Profiles listed below.

## Summary and Scope

Core 0.2 defines immutable release identity, capability contract identity,
typed messages, stream ordering, durable acknowledgement, bounded replay,
resume, Artifact commit, structured errors, and authoritative Run outcomes.

## Architecture and Module Boundaries

| Component | Authority |
|---|---|
| Host admission | Tenant, principal reference, release, capability, policy, limits, idempotency. |
| Transport adapter | Framing, stream epoch, sequence, ACK, replay, liveness, backpressure. |
| Agent | Declared capability execution and proposed outputs within received grants. |
| Artifact store | Byte integrity, commit receipt, access scope, retention handle. |
| Run ledger | State transitions, critical events, receipts, terminal record, reconciliation status. |
| Profile adapter | Effects, grants, secrets, isolation, audit/data, or remote mapping. |

## State Machine and Lifecycle

```text
queued -> starting -> running -> input_required -> running
                         |----> approval_required -> running
                         |----> reconciling
                         `----> succeeded | failed | cancelled | timed_out | indeterminate
```

- Only the Host writes the authoritative state.
- Every transition records actor, prior state, new state, event ID, time, and
  policy/reason code where applicable.
- Terminal states are immutable and mutually exclusive.
- `indeterminate` is terminal for the original Run. A reconciliation operation
  creates linked evidence; it does not rewrite history.
- `succeeded` requires valid output plus all required Artifact receipts and all
  Effect completion conditions declared by negotiated Profiles.

## Data Model and Canonical Identity

### Release

```json
{
  "agent_id": "com.example.agent",
  "version": "2.0.0",
  "package_digest": "sha256:<hex>",
  "manifest_digest": "sha256:<hex>",
  "capability_contracts": {
    "invoice.extract": "sha256:<hex>"
  }
}
```

The package digest covers the complete canonical package tree. Signature
profiles attest to it but do not change it. JSON canonicalization uses RFC 8785
or a future explicitly versioned LAP canonicalization algorithm; Hosts MUST NOT
use language-dependent serialization.

The capability digest covers capability ID, canonical input/output schemas,
Artifact contract, Effect contract, required profiles, and permission request
declarations. Any change creates a new release identity even when the human
version string was incorrectly reused.

### Stream

```json
{
  "stream_id": "opaque-host-issued-id",
  "epoch": 3,
  "seq": 42,
  "event_id": "opaque-event-id",
  "causation_id": "originating-event-id"
}
```

`stream_id` is bound to one peer pair and Run or activation probe. A new writer
lease increments `epoch`; older epochs are fenced. Sequence starts at one for
each epoch and strictly increases. The de-duplication key is
`(stream_id, epoch, seq)`.

## API/Event Contracts

Every message has an independent JSON Schema and fixes sender, required
Envelope fields, payload, legal prior state, idempotency behavior, and error
mapping.

The draft source of truth is
[`../schemas/core-0.2/envelope.schema.json`](../schemas/core-0.2/envelope.schema.json).
Each payload contract is published as a stable `$defs` fragment and registered
by JSON Pointer in `registry.json`; this keeps one self-contained validation
document while allowing each message to be addressed independently. The
envelope carries an explicit `sender` role. A receiving transport adapter MUST
compare it with the authenticated or negotiated peer; the field alone grants
no authority.

| Message | Sender | Critical | Required outcome |
|---|---|---:|---|
| `agent.hello` | Host | yes | Offers Core/Profile versions and expected release/contract digests. |
| `agent.welcome` | Agent | yes | Selects versions and echoes its actual release/contract digests. |
| `agent.probe` | Host | yes | Requests no-side-effect readiness and dependency status. |
| `agent.probe.result` | Agent | yes | Reports contract match and bounded readiness facts without secret values. |
| `run.start` | Host | yes | Creates or replays one idempotent Run admission. |
| `run.accepted` | Agent | yes | Correlates to `run.start` and accepts responsibility. |
| `run.progress` | Agent | no | Reports bounded observable progress. |
| `artifact.offer` | Agent | yes | Proposes immutable output metadata and a profile-resolvable source. |
| `artifact.committed` | Host | yes | Returns receipt ID, canonical private reference, digest, size, and scope. |
| `run.input_required` | Agent | yes | Requests bounded structured input without changing authority. |
| `run.input_response` | Host | yes | Supplies validated response or explicit decline. |
| `run.cancel` | Host | yes | Requests cancellation with reason and deadline. |
| `run.cancelled` | Agent | yes | Confirms work stopped; Host still decides terminal state. |
| `run.result` | Agent | yes | Proposes one terminal result referencing committed receipts. |
| `run.result.ack` | Host | yes | Confirms durable authoritative terminal record. |
| `run.resume` | Host | yes | Supplies last durable waterline and resume token. |
| `run.snapshot` | Agent | yes | Returns current state, critical-event waterline, and replay availability. |
| `stream.ack` | Either | yes | Confirms durable application through a contiguous sequence. |

Profile messages such as `effect.*`, `grant.*`, `approval.*`, and `secret.*`
are not registered by Core until their own LEPs are accepted.

### Artifact contract

An offer contains `artifact_id`, name, media type, byte size, SHA-256, source
reference, delivery policy, and semantic role. For a required Artifact, size,
digest, resolvable source, and delivery policy are mandatory.

The Host validates path/reference scope, quota, content digest, media policy,
malware/content rules, tenant ownership, and requested retention. It then
persists bytes and returns an opaque receipt. Repeating the same
`artifact_id + sha256` returns the same receipt; the same ID with different
bytes is `LAP-109`.

`run.result` contains `artifact_receipt_ids`. Repeating Artifact metadata in
the result is prohibited. A missing required receipt makes success invalid.

## Business Logic and Edge Cases

- A contract mismatch fails activation before Run input is disclosed.
- A stale epoch cannot write, cancel, commit an Artifact, or propose a result.
- A sequence gap pauses critical-event application and initiates bounded replay;
  it does not invent an event.
- Replayed messages produce the prior durable response.
- A duplicate terminal proposal cannot change the authoritative outcome.
- Cancellation racing with result uses the first valid Host-persisted terminal
  transition; later evidence is retained as an anomaly.
- A required Artifact commit failure prevents success.
- Provider acceptance is never mapped to Effect completion.
- If an external effect may have occurred and reconciliation cannot prove its
  state by deadline, the Run becomes `indeterminate`.

## Error Handling, Retries, and Idempotency

The existing ranges remain, with a single machine-readable registry. Errors
add optional safe fields:

```json
{
  "code": "LAP-101",
  "message": "Output violates the declared capability contract.",
  "retryable": false,
  "phase": "output_validation",
  "json_pointer": "/requests",
  "constraint": "additionalProperties",
  "cause_code": "CONTRACT_OUTPUT_MISMATCH",
  "responsibility": "agent",
  "operator_correlation_id": "opaque-id",
  "recovery": {"action": "upgrade_release"}
}
```

Retry policy is derived from code plus state, never message text. A retryable
transport failure does not imply an external effect is safe to repeat.

## Security and Authorization

- Tenant and principal are Host-issued and never accepted from Agent input.
- Resume and receipt tokens are unguessable, audience-bound, scoped, and
  revocable.
- Contract schemas are self-contained and never trigger ambient retrieval.
- Long-lived credentials are prohibited from Core messages.
- Artifact references cannot expose private Host filesystem paths.
- Sensitive values are redacted before audit and diagnostics.
- Commercial Host claims require protected access transport; HTTP pilot mode is
  explicitly outside that claim.

Grant, approval, Secret Broker, isolation, and data-governance requirements are
specified by separate Profiles. Absence of a profile cannot be interpreted as
implicit authority.

## Performance Budgets

- Core frame maximum defaults to 1 MiB; Artifact bytes are never embedded in a
  Core frame unless a negotiated transfer Profile permits it.
- ACK batching may cover a contiguous sequence but MUST NOT acknowledge data
  not yet durably applied.
- Replay retention is bounded by bytes, count, and time and is advertised at
  negotiation.
- Backpressure limits and heartbeat intervals are negotiated and recorded.
- A Host must reject work before dispatch when it cannot reserve the required
  durable ledger or Artifact capacity.

## Observability and Operations

W3C `traceparent` and `tracestate` are carried in a defined extension. Standard
metrics include admissions, active Runs, transition latency, ACK latency,
replay depth, gaps, stale epochs, Artifact commit latency/failure, terminal
conflicts, unknown Effects, and reconciliation duration.

Content-bearing telemetry is opt-in and classified as sensitive. Required
protocol telemetry contains identifiers, digests, state, timing, sizes, policy
decision references, and safe codes only.

## Testing Strategy

| Test ID | Scenario | Required evidence |
|---|---|---|
| C02-WIRE-01 | Every message validates only its legal sender/shape/state | positive and negative schema vectors |
| C02-CONTRACT-01 | Running digest differs from package | activation rejected before context |
| C02-STREAM-01 | Agent restart resets seq under new epoch | no duplicate suppression collision |
| C02-STREAM-02 | ACK lost after durable apply | replay returns prior response without duplicate state |
| C02-STREAM-03 | stale writer emits result | fenced and audited |
| C02-RESUME-01 | Host or Agent restarts mid-Run | snapshot/replay restores provable state |
| C02-ART-01 | required Artifact commits | receipt precedes successful terminal ACK |
| C02-ART-02 | digest/path/quota mismatch | typed failure, no exposed deliverable |
| C02-ART-03 | duplicate offer | same receipt or conflict on changed digest |
| C02-RUN-01 | cancel and result race | exactly one terminal ledger record |
| C02-RUN-02 | external outcome cannot be proven | `indeterminate`, no blind retry |
| C02-ERR-01 | contract violation | JSON pointer and safe recovery action present |
| C02-SEC-01 | cross-tenant receipt/resume replay | rejected without existence disclosure |

The TCK must inject half frames, invalid UTF-8, oversized frames, duplicate and
out-of-order events, process kill, storage failure, lost responses, and Host
failover. Reports are complete, signed attestations bound to source, binary,
package, TCK, and environment digests.

The published draft registry is
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json). It
must list every row above exactly once and declare the current evidence state.
While its `claimability.status` is `not_claimable`, no implementation may make
a Core 0.2 conformance claim; draft Schema evidence is not a Host runtime
attestation.

## Implementation Plan

1. Accept this LEP and freeze new Core 0.1 features.
2. Add canonicalization and message schemas.
3. Add TCK registry and mandatory coverage validation.
4. Implement stream ledger, ACK, replay, resume, and fencing.
5. Implement Artifact store receipts and terminal gating.
6. Implement structured errors and terminal `indeterminate`.
7. Publish a migration adapter and compatibility matrix.
8. Implement separate commercial Profiles through their own LEPs.
9. Validate against a second independent Host before 1.0.

## Open Questions and Risks

No Core design question blocks implementation. The largest delivery risk is
attempting all commercial Profiles in one release. They must ship separately
behind explicit negotiation and conformance gates.

## Traceability Matrix

| Source | Downstream contract | Test evidence | Status |
|---|---|---|---|
| US-001 Contract-safe activation | Release/capability digests and probe | C02-CONTRACT-01 | covered |
| US-002 Recover interrupted work | stream epoch, ACK, replay, resume | C02-STREAM-01..03, C02-RESUME-01 | covered |
| US-003 Receive durable deliverables | Artifact offer/commit receipt | C02-ART-01..03 | covered |
| US-004 Understand external outcomes | Effect Profile boundary and `indeterminate` | C02-RUN-02; future Effect TCK | profile follow-up |
| FR-001 Typed messages | per-message Schema registry | C02-WIRE-01 | covered |
| FR-002 One terminal outcome | Host state machine | C02-RUN-01 | covered |
| FR-003 Tenant isolation | scoped receipt/resume tokens | C02-SEC-01 | covered |
| FR-004 Actionable errors | structured error registry | C02-ERR-01 | covered |
| FR-005 Independent interoperability | complete signed TCK report | second-Host matrix | 1.0 gate |
