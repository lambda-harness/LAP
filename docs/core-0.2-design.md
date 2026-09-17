# Design: LAP Commercial-Grade Protocol Framework

## Status

Accepted for specification. Draft Schema, vector, TCK-registry, and reference
stream/Artifact/Run state-machine plus scoped-token work exists; no Core 0.2
Host runtime adapter has started.

## Abstract

LAP will mature as the portable contract between an enterprise Host and a
managed business Agent. Core 0.2 closes four outcomes that must be true before
commercial use: the running contract matches the admitted release, interrupted
work can be recovered without guessing, required deliverables are durably
committed before success, and external side effects carry evidence distinct
from Agent-process success.

## Background and Evidence

Core 0.1 already provides a strong base: Host authority, immutable release
resolution, strict input/output contracts, idempotent Run admission, one
terminal state, tenant isolation, package signing, and constrained workflow
dispatch.

The remaining gaps are systemic:

- the Envelope schema does not constrain each payload shape;
- stable producer IDs and reset sequence numbers collide after restart;
- reconnect has no ACK waterline, replay retention, resume, or fencing;
- Artifact delivery has policy but no commit transaction;
- grants are reserved and permissions are free-form requests;
- external effects cannot express accepted, settled, or unknown outcomes;
- Local supervision is not execution isolation;
- conformance reports can be incomplete self-attestations.

## Design

### Product boundary

```text
Enterprise Host Baseline
  identity, RBAC/ABAC, TLS, KMS, HA/DR, SIEM, storage
        |
LAP Core 0.2
  release, contract, run, event, artifact, error, recovery
        |
Managed Profiles
  grants/approval, effects, secrets, isolation, audit/data, provenance
        |
Interoperability Bridges
  MCP tools, A2A remote agents, ACP interactive clients
```

Core defines only behavior that two independent Hosts and Agents must share.
Deployment products choose databases, identity providers, gateways, object
stores, sandboxes, and user experience.

### Reliability model

LAP promises idempotent Run admission, at-least-once critical event delivery,
idempotent state application, and exactly one authoritative terminal record.
It does not promise exactly-once network delivery or exactly-once execution by
an arbitrary external system.

Critical events are accepted/rejected Run admission, Artifact offer/commit,
approval and grant decisions, Effect transitions, cancellation, and terminal
result. Progress is observable but expendable.

### Contract identity

The Host computes a canonical digest of the complete admitted package and each
capability contract. Negotiation compares those digests with the running
implementation. A mismatch fails activation, before any business input or
credential is provided.

### Artifact transaction

```text
Agent                    Host                         User/workflow
  | artifact.offer        |                               |
  |---------------------->| validate/copy/scan/digest     |
  | artifact.committed    |                               |
  |<----------------------| stable receipt + private ref  |
  | run.result(receipt)   |                               |
  |---------------------->| persist terminal              |
  |                       |------------------------------>|
```

Required Artifacts participate in the success transaction. Optional Artifacts
may fail with a typed warning, but their failure cannot be hidden.

### Effect transaction

External side effects live in a separate Profile:

```text
intent -> authorized -> accepted -> settled
                              \-> failed
                              \-> unknown -> reconciling -> settled|failed|indeterminate
```

`accepted` means the provider acknowledged the request, not that the business
operation completed. An unknown outcome is never retried until policy and the
provider-specific reconciliation method prove it safe.

### Security model

Agents receive pseudonymous principal references and narrowly scoped,
short-lived grants. Long-lived secrets remain in a Host-controlled broker.
Package signature, user approval, grant issuance, execution isolation, and
tenant admission are separate decisions.

Commercial deployment requires protected transport at the access boundary.
The current fixed-IP HTTP mode remains an explicitly labelled internal pilot
mode and cannot claim high-assurance profiles.

## Rationale and Trade-offs

This design adds protocol states and durable storage requirements. That cost is
intentional: ambiguity is more expensive when Agents deploy software, change
data, or deliver regulated documents. Keeping non-portable enterprise choices
outside Core prevents the specification from becoming a Lambda Harness product
API.

## Rejected Alternatives

- A single broad `permissions` string list cannot express actor, resource,
  audience, expiry, delegation, or revocation.
- Retrying every disconnected call is unsafe for external side effects.
- A successful subprocess exit is not proof of Artifact delivery or business
  completion.
- A signature is provenance evidence, not authorization or sandbox evidence.
- Adding more Agent examples before closing protocol invariants would expand
  the unsupported surface.

## Compatibility and Migration

Core 0.2 is a deliberate pre-1.0 breaking boundary. Hosts may offer separate
0.1 and 0.2 adapters. Existing 0.1 releases keep their current semantics until
drained; only rebuilt and revalidated releases can serve 0.2 Runs.

Profiles version independently. A peer that does not negotiate a required
profile is rejected before receiving context or starting work. External
specifications must be pinned to explicit versions rather than `latest`.

## Rollout, Rollback, and Observability

1. Publish accepted Core schemas and vectors without enabling production Runs.
2. Add a shadow validator to compare 0.1 traffic with proposed 0.2 contracts.
3. Enable 0.2 only for reference Agents and synthetic fault tests.
4. Canary low-risk read-only Agents.
5. Enable Artifact transactions, then Effects, then security profiles.
6. Retain the 0.1 adapter until all active releases drain.

Rollback selects the prior adapter and immutable release; it never rewrites an
in-flight Run. Metrics include negotiation failures, replay depth, stale epoch
rejections, Artifact commit latency, Effect unknown duration, reconciliation
outcomes, and terminal conflicts.

## Implementation/Transition

The implementation order is:

1. schemas, canonicalization, digests, and complete conformance registry;
2. stream epoch, durable ACK, replay, resume, and fencing;
3. Artifact commit receipts;
4. structured errors and `indeterminate`;
5. Effect, Grant/Approval, Secret Broker, Isolation, Audit/Data profiles;
6. remote Artifact transfer and package provenance;
7. independent Host implementation and security assessment.

## Open Questions

Profile details such as broker transport, isolation evidence, Effect provider
adapters, and audit sink attestations require separate LEPs. They do not block
the Core 0.2 specification.
