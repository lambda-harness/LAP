# LEP-0010: Commercial-Grade Core 0.2

- **Status:** Accepted
- **Type:** Standards Track
- **Target version:** `0.2.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-09-17`
- **Requires:** LAP Core 0.1
- **Supersedes:** None
- **Superseded by:** None

## Summary

LAP Core 0.2 will make managed Agent execution recoverable and mechanically
verifiable. It introduces typed wire messages, immutable release and contract
digests, stream epochs, critical-event acknowledgement, resumable run state,
transactional Artifact delivery, structured diagnostics, and an explicit
`indeterminate` outcome for externally observable work whose final state cannot
yet be proven.

LAP remains an enterprise Agent delivery and execution contract. MCP remains
the tool interoperability layer, A2A the remote Agent transport, and ACP the
interactive Agent-client layer.

## Motivation

Core 0.1 defines the correct trust boundary but leaves material behavior to
Host implementations. The generic Envelope accepts arbitrary payload objects;
`(producer, seq)` can collide after process restart; reconnect has no ACK,
cursor, or fencing semantics; a required Artifact has no commit receipt; and a
successful Run cannot distinguish an external request being accepted from the
business operation being completed.

These gaps appeared in real integrations: a manifest output contract diverged
from the running Agent, and an Agent reported a workbook without a resolvable
output URI. Both failures were detected late. Core 0.2 moves those failures to
activation or a typed transactional boundary.

## Scope and Non-Goals

Core 0.2 covers:

1. exact schemas for every Core message;
2. full-package and per-capability contract identity;
3. ordered stream epochs, critical-event ACK, bounded replay, and resume;
4. durable Artifact offer/commit receipts;
5. a structured error and recovery model;
6. one authoritative Run state machine, including `indeterminate`.

Separate profiles will define Effect execution, grants and approvals, Secret
Broker access, execution isolation, audit/data policy, package provenance, and
remote Artifact transfer.

Core does not define OA/OIDC login, RBAC storage, databases, object stores,
sandbox technology, TLS termination, workflow UI, MCP tools, model APIs, or
external-provider completion semantics.

## Normative Design

The detailed proposed contract is in
[`docs/core-0.2-spec.md`](../docs/core-0.2-spec.md). Its key decisions are:

- Every release MUST have a Host-calculated canonical `package_digest` even
  when it is unsigned. A signature proves provenance; it does not create the
  content identity or grant authority.
- Every capability MUST have canonical input, output, Artifact, and Effect
  contract digests. The running Agent MUST echo the combined contract digest
  during negotiation and activation probe.
- Every stream MUST have a Host-issued unpredictable `stream_id` and positive
  `epoch`. Ordering and de-duplication use `(stream_id, epoch, seq)`.
- Only critical state-changing messages require durable acknowledgement.
  Progress remains best-effort and MUST NOT block terminal completion.
- A receiver MUST durably apply a critical event before acknowledging it.
  Delivery is at least once; state transitions and side effects are idempotent.
- A required output is successful only after `artifact.committed`. A terminal
  result references Artifact receipt IDs rather than redefining their metadata.
- A Host MUST record exactly one terminal Run outcome. It MUST use
  `indeterminate` when an external effect may have occurred but available
  evidence cannot prove completion or non-execution.

## Security, Tenancy, and Authorization

The Host remains authoritative for tenant, principal, release, policy, grants,
approval, storage, and terminal state. Stream and resume tokens are scoped to
one tenant, Run, release, and transport peer. An Agent-supplied tenant, grant,
receipt, policy decision, or terminal state is untrusted until the Host
validates and persists it.

Core messages MUST NOT contain long-lived credentials, unrestricted filesystem
paths, broad caller tokens, or hidden reasoning. Commercial deployments use a
future Secret Broker Profile and protected transport. Fixed-IP HTTP operation
is a Host pilot mode and cannot claim the commercial security deployment
profile.

## Privacy and Observability

Core 0.2 standardizes W3C Trace Context carriage and safe correlation fields.
Raw prompts, model outputs, credentials, personal identifiers, Artifact bytes,
and provider responses are opt-in sensitive content and are not mandatory
telemetry. Audit and data retention semantics remain profile-owned.

## Compatibility and Migration

This is a breaking draft revision before LAP 1.0. A Core 0.1 peer MUST NOT be
silently upgraded to Core 0.2 behavior. A dual-version Host may run 0.1 and 0.2
adapters side by side, but one Run is pinned to one negotiated Core version and
one immutable release.

Existing 0.1 Runs drain under 0.1. Rebuilt Agents declare 0.2, include the new
schemas, and pass activation probing before receiving 0.2 Runs. No adapter may
invent Artifact receipts or Effect completion evidence for a 0.1 Agent.

## Conformance Plan

Core 0.2 will add executable assertions for:

- complete per-message schema rejection;
- package and capability contract mismatch;
- epoch restart, duplicate, gap, replay-window, and stale-writer fencing;
- crash before and after durable ACK;
- Artifact digest mismatch, commit failure, duplicate offer, and receipt use;
- cancellation/result races and exactly one terminal record;
- `indeterminate` plus reconciliation handoff;
- structured diagnostics without secret or tenant leakage.

Fault injection MUST cover half frames, invalid UTF-8, restart, lost ACK,
duplicate delivery, storage failure, Host failover, and external-call response
loss. A conformance claim requires every mandatory assertion for the claimed
profile; self-selected subsets are invalid.

## Reference Implementation Plan

Lambda Harness will implement the first Host adapter and Python/Go reference
Agents. A second independently implemented Host is required before LAP 1.0.
The same signed Agent package must complete black-box tests on both Hosts
without business-code changes.

## Alternatives Considered

| Alternative | Decision |
|---|---|
| Keep Core 0.1 and add implementation conventions | Rejected: interoperability cannot depend on undocumented Host behavior. |
| ACK every event | Rejected: progress traffic would add latency and backpressure without protecting state. |
| Claim exactly-once transport | Rejected: crashes and external systems make that promise misleading. |
| Put OA, OAuth, KMS, and sandbox APIs in Core | Rejected: these are Host or profile concerns and would destroy portability. |
| Replace LAP with MCP or A2A | Rejected: neither defines LAP's immutable local release, Host policy, and governed delivery boundary. |

## Open Questions

No unresolved question blocks the Core 0.2 Design phase. Profile-specific wire
contracts require separate LEPs before implementation.

## Resolution Record

- **Decision:** Accepted
- **Decision date:** `2026-09-17`
- **Target release:** `0.2.0-draft`
- **Rationale:** The maintainer approved the narrowed positioning, one pre-1.0
  breaking revision, Host-authoritative effects/grants, protected commercial
  transport baseline, `indeterminate` outcome, and independent-Host 1.0 gate.
- **Required follow-up:** Complete the Core 0.2 schemas, conformance vectors,
  reference Host, reference Agents, security review, and migration guide.
