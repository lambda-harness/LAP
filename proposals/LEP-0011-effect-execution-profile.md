# LEP-0011: Host-governed effect execution profile

- Status: Accepted
- Target: `0.2.0-draft`
- Authors: LAP maintainers

## Summary

Add `lap-effect/0.1`, a provider-neutral profile for external side effects.
The profile makes authorization, approval, provider evidence, reconciliation,
and required-effect settlement part of the Host contract instead of allowing
an Agent to report an attached success field.

## Motivation

Business Agents increasingly trigger releases, uploads, payments, and other
operations whose transport acknowledgement is not the business outcome. Core
Run terminal semantics need a reusable Host-owned boundary that can distinguish
accepted, settled, failed, and unknown effects without embedding Jenkins or
another provider into the protocol.

## Normative decision

The Host supplies immutable effect rules in the scoped capability context. An
Agent proposes only a bounded intent. The Host controls authorization and
approval, executes the provider, stores opaque evidence references, and
reconciles unknown outcomes. A required effect must be terminally settled in
the same durable transaction as a successful Run; otherwise the Run is rejected
with `LAP-104`. Terminal effects are immutable and never automatically retried.

## Compatibility

This is an additive profile and does not change the Core envelope. Hosts that
do not implement the profile must not claim `lap-effect/0.1` compatibility.
Existing Agents can continue to return ordinary Run results, but side-effecting
capabilities must not claim this profile until they implement the complete
Host boundary.

## Acceptance evidence

The reference ledger, JSON schema, and conformance vector are committed under
`src/lap_protocol/effect_ledger.py`, `schemas/`, and `conformance/`. The Core
Run ledger integrates the required-effect success gate through an optional
Host-owned effect ledger.
