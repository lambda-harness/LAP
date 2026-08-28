# LEP-XXXX: Short Title

- **Status:** Draft
- **Type:** Standards Track | Process | Informational
- **Target version:** `0.x`
- **Authors:** `@github-handle`
- **Created:** `YYYY-MM-DD`
- **Requires:** None | LEP-NNNN
- **Supersedes:** None | LEP-NNNN
- **Superseded by:** None | LEP-NNNN

## Summary

State the proposed outcome in two or three sentences. Identify the affected
LAP Core or profile version.

## Motivation

Describe the interoperable problem, affected implementers, and why existing
LAP behavior is insufficient. Separate observed facts from assumptions.

## Scope and Non-Goals

List the behavior this LEP changes and the adjacent behavior it deliberately
does not change.

## Normative Specification

Use RFC 2119 terms (`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, `MAY`) only for
requirements. Define inputs, outputs, ordering, timeouts, idempotency,
terminal behavior, and typed errors where applicable. Include exact envelope,
schema, or profile deltas rather than relying on prose examples.

## Security, Tenancy, and Authorization

Explain the trust boundary, actor identities, least-privilege implications,
approval behavior, secret handling, package/provenance impact, and tenant data
isolation. State why an untrusted Agent cannot use the change to broaden its
authority.

## Privacy and Observability

List any new persisted, emitted, or redacted fields. Progress events MUST
describe externally meaningful operations and outcomes; they MUST NOT require
hidden model reasoning.

## Compatibility and Migration

Classify the change as additive, behavior-tightening, or breaking. Describe
feature negotiation, downgrade behavior, release activation, draining of
in-flight work, and the migration path for Hosts and Agents.

## Conformance Plan

List new or changed conformance assertion IDs, portable vectors, schemas, and
negative tests. Explain how independent implementations can reproduce the
claim without relying on an author-controlled service.

## Reference Implementation Plan

Identify any reference Host, Agent, SDK, or test-kit work. Reference work is
evidence, not a substitute for the normative specification or conformance
tests.

## Alternatives Considered

Compare materially different protocol designs, including doing nothing. State
why this proposal is the smallest compatible solution.

## Open Questions

List unresolved questions that block acceptance. Remove or resolve them before
marking the LEP Accepted.

## Resolution Record

Maintainers fill this section when the proposal reaches a terminal status:

- **Decision:** Accepted | Rejected | Withdrawn | Superseded
- **Decision date:** `YYYY-MM-DD`
- **Target release:** `version` | Not applicable
- **Rationale:**
- **Required follow-up:**
