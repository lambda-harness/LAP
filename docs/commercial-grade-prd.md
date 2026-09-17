# PRD: Commercial-Grade LAP Protocol Framework

## Overview

LAP must let enterprise platform teams admit independently delivered business
Agents, run them under Host policy, recover interrupted work, and deliver
verifiable results without depending on Agent implementation details.

## Goals

- Detect release and contract drift before business execution.
- Recover interrupted Runs without duplicating work or guessing outcomes.
- Make required deliverables available before reporting success.
- Distinguish Agent completion, provider acceptance, and business completion.
- Provide portable authorization, security, audit, and conformance boundaries.
- Preserve LAP's focused role alongside MCP, A2A, and ACP.

## User Stories

### US-001: Contract-safe activation

As a platform operator, I need the Host to prove that the running Agent matches
the admitted package and declared capability contracts before it receives user
input or credentials.

Acceptance criteria:

- Changing executable, manifest, or capability contract bytes changes the
  admitted identity.
- A negotiation or probe digest mismatch prevents activation.
- The failure identifies the mismatched contract without exposing secrets.

### US-002: Recover interrupted work

As an operator, I need a Host or Agent restart to resume from durable evidence
so that work is neither silently lost nor repeated.

Acceptance criteria:

- Duplicate critical events do not duplicate state or side effects.
- Stale writers cannot change a Run after failover.
- When replay is unavailable, the Run exposes a typed, truthful outcome.

### US-003: Receive durable deliverables

As a business user, I need a successful Run's required files to be immediately
available through an authorized Host link.

Acceptance criteria:

- Success is not recorded before every required Artifact is committed.
- Artifact bytes are verified against size and digest.
- Repeated delivery is idempotent and cross-tenant access is denied.

### US-004: Understand external outcomes

As an operator or approver, I need to distinguish a requested action, an
accepted provider job, a completed business action, and an unknown outcome.

Acceptance criteria:

- Provider acceptance is never displayed as business completion.
- Unknown outcomes enter reconciliation and are not blindly retried.
- Authorization, approval, and external receipts are independently auditable.

### US-005: Trust a conformance claim

As an enterprise adopter, I need a LAP conformance claim to represent every
mandatory test for its declared Core and Profiles.

Acceptance criteria:

- Missing, duplicate, failed, or unjustified assertions invalidate the claim.
- Evidence is bound to source, package, binary, TCK, and environment identity.
- The same Agent package passes black-box interoperability on two independent
  Hosts before LAP 1.0.

## Functional Requirements

- **FR-001:** LAP shall define an exact Schema for every Core message.
- **FR-002:** LAP shall identify every release and capability contract by a
  canonical content digest.
- **FR-003:** LAP shall order and de-duplicate events across process restarts.
- **FR-004:** LAP shall durably acknowledge every state-changing event.
- **FR-005:** LAP shall support bounded replay and evidence-based resume.
- **FR-006:** LAP shall commit required Artifacts before successful completion.
- **FR-007:** LAP shall represent uncertain external outcomes explicitly.
- **FR-008:** LAP shall expose structured, safe, actionable errors.
- **FR-009:** LAP shall keep grants, approval, secrets, and effects under Host
  authority through negotiated Profiles.
- **FR-010:** LAP shall require complete executable evidence for a conformance
  claim.

## Non-Goals

- Standardizing model prompts, planning, memory, or hidden reasoning.
- Replacing MCP, A2A, ACP, OAuth/OIDC, OpenTelemetry, or supply-chain standards.
- Defining Lambda Harness UI, storage, database, or deployment technology.
- Promising exactly-once network delivery or arbitrary provider execution.
- Making package signatures equivalent to permission or sandbox trust.

## Design Considerations

The product must remain useful for local scripts and binaries while allowing
commercial Hosts to require stronger Profiles. User-visible language must be
truthful: `accepted`, `completed`, and `indeterminate` are distinct outcomes.
Pilot HTTP deployments remain possible but cannot claim the protected
commercial deployment level.

## Technical Considerations

- Core 0.2 may make one deliberate breaking change before LAP 1.0.
- Existing 0.1 Runs drain under their original semantics.
- External specifications are pinned to explicit versions.
- Security, Effect, Secret, Isolation, Audit/Data, and Provenance behavior is
  independently negotiated and versioned.

## Success Metrics

- 100% of registered Core message types have positive and negative vectors.
- 100% of mandatory profile assertions are present in a valid claim.
- No injected duplicate, lost ACK, restart, or failover scenario creates two
  authoritative terminal records.
- No successful Run lacks a committed required Artifact.
- No test maps provider acceptance to business completion.
- One identical Agent package passes the release gate on two independent Hosts
  without business-code changes.

## Open Questions and Assumptions

The scope and product decisions are approved. Separate Profile LEPs must decide
broker transports, isolation evidence, Effect-provider reconciliation, audit
sink attestations, and remote Artifact transfer. Those decisions do not block
Core 0.2 implementation.
