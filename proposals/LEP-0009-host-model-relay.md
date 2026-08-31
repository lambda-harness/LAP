# LEP-0009: Host Model Relay for Metered Local Agents

- **Status:** Draft
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-31`
- **Requires:** LAP Core 0.1, `lap-local/0.1`, `lap-host-metering/0.1`, LEP-0005, LEP-0006
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal defines `lap-model-relay/0.1`, a Local-profile extension through
which an external Agent asks a Host to perform a model request. The Host sees
the actual pre-provider request and provider response, so it can use the same
workflow meter and ledger as native Agents.

Agent-reported token or cost fields remain observability only. A Host may use
the profile for a strict external budget only when deployment isolation blocks
the Agent from bypassing the relay to reach model providers directly.

## Motivation

LAP's current Host Metering Profile deliberately rejects strict input, output,
and cost budgets for an external Local, A2A, or nested Agent transport. The
Host cannot verify an independent Agent's direct provider calls, and a signed
Agent package does not make its self-reported usage billing evidence.

That conservative rejection preserves tenant and cost integrity, but it also
means an installable coding Agent cannot participate in a tightly budgeted
workflow even when an operator is willing to provide a Host-owned model route.
The missing boundary is not another usage field. It is a request path that the
Host can observe, reserve, settle, cancel, and audit.

## Scope and Non-Goals

This proposal defines one first-class path:

1. A supervised Local Agent negotiates `lap-model-relay/0.1` together with
   `lap-local/0.1`.
2. The Host grants only named, release-authorized model routes in the Context
   Packet. It never gives the Agent a provider endpoint, API key, or tenant
   credential.
3. The Agent emits a profile-owned `model.request`; the Host validates the
   exact request, reserves quota, performs the provider call, settles its
   ledger, and emits one `model.response`.
4. The Host claims strict external metering only after an operator-enforced
   deny-by-default egress policy proves the Local process cannot reach any
   model-capable network path outside the relay for that Run.

This proposal does not standardize a provider's request API, provider invoices,
remote Agent attestation, delegated credentials, sandbox technology, streaming
token deltas, or an Agent's right to select arbitrary models or tools. A remote
or independently hosted Agent remains outside strict metering unless a later
proposal defines verifiable request/usage evidence with equivalent authority.

## Proposed Wire Contract

The profile identifier is `lap-model-relay/0.1`. Its Context Packet extension
key is `io.github.lambda-harness.lap.model-relay` and its payload validates
against `schemas/model-relay-context.schema.json`.

The context contains a sorted, non-empty list of opaque Host route IDs with
per-route request and output ceilings. A route ID is not a provider model name,
network address, or authorization grant.

After `run.accepted`, an Agent may emit a `model.request` Core Envelope scoped
to the same Run. The envelope MUST carry a new idempotency key and a payload
validating against `schemas/model-relay-request.schema.json`. The Host replies
with exactly one `model.response` correlated to the Agent request ID, with a
payload validating against `schemas/model-relay-response.schema.json`.

`model.request` and `model.response` are proposed profile-owned envelope types.
They are intentionally not yet registered by LAP Core 0.1; adoption requires a
companion Core registry update and reference runtime support. Until then, no
implementation may claim this profile merely by accepting the schemas.

The Host canonicalizes the actual post-policy provider request and records its
SHA-256 in `model.response.request_sha256`. Replaying an equivalent Agent
idempotency key returns the original response without another provider call.
Reusing it with a different canonical request fails with `LAP-201` before any
provider call.

## Strict Metering Admission

Before an external node with a strict workflow budget starts, the Host MUST
verify all of the following:

1. The exact validated Local release declares and negotiates
   `lap-model-relay/0.1` for this Run.
2. The selected capability and release are authorized for every granted route.
3. The Host's `lap-host-metering/0.1` configuration is valid and shares the
   root workflow ledger.
4. Deployment-controlled egress isolation for the spawned process is active,
   denies outbound network access by default, and allows only the Host relay
   endpoints required for the Run. Blocking a known provider domain alone is
   not sufficient evidence.
5. No nested execution path covered by the strict budget can consume models
   outside the same Host ledger.

A failed negotiation is `LAP-204`; a denied route or missing isolation is
`LAP-302`; a quota or route ceiling failure is `LAP-401`. Each rejection occurs
before the relevant provider call. A Host MUST NOT replace this admission with
an Agent declaration, package signature, process environment variable, or
post-hoc usage report.

## Security and Privacy

The Local stdio channel and validated run identity bind each relay request to
one exact release, tenant, session, capability, and Run. Context carries only
opaque route identifiers and finite ceilings. Provider credentials, provider
URLs, raw tenant policy, internal prompt templates, and unrestricted tool
grants remain Host-private.

The Host writes audit facts for negotiated profile, route, request digest,
reservation, settlement source (`provider` or conservative `reservation`),
and terminal rejection. It MUST NOT write raw prompts, raw model outputs,
provider credentials, or hidden reasoning to public audit records.

An operator-provided egress rule is an enforcement prerequisite, not evidence
supplied by the Agent. A Host that cannot prove the rule is active must retain
the current fail-closed external-budget behavior.

## Compatibility and Migration

The profile is additive. Existing Local Agents continue to negotiate only
`lap-local/0.1`; Hosts must not send model-relay context or accept
`model.request` from them. A new Agent adds the profile to its manifest and
`agent.welcome`, then is rebuilt and re-activated as a new immutable release.

This proposal does not loosen the existing strict-budget rejection for any
external transport. That behavior changes only with an implemented relay,
validated profile negotiation, and deployment isolation evidence.

## Conformance Plan

`conformance/model-relay.json` fixes the draft Context, request, response,
idempotent replay, and pre-provider rejection cases. The vector proves the
portable contract, not a Host's provider adapter or sandbox. A future
Implemented profile claim must add executable Local round-trip evidence and
the matching rows in `CONFORMANCE.md`.

`tools/lap_model_relay_probe.py` and the Python reference Agent provide that
draft round-trip evidence with a deterministic simulated Host response. They
do not contact a provider, certify a Host, or satisfy the isolation prerequisite
for a production metering claim.

## Alternatives Considered

| Alternative | Decision |
|---|---|
| Trust an Agent's `usage` result fields | Rejected: self-report cannot enforce a pre-provider budget or prove absence of bypass calls. |
| Give the Agent a provider API key | Rejected: it expands credential exposure and removes Host request control. |
| Standardize provider-signed receipts first | Deferred: common provider receipt semantics do not yet provide a portable, request-bound contract. |
| Allow relay without egress isolation under a strict budget | Rejected: the Agent could make unmetered direct calls. |
| Change Core envelope types immediately | Deferred: profile semantics, schemas, and reference behavior must be reviewed together before a current Core claim. |

## Open Questions

1. Which deployment-neutral isolation evidence can be standardized without
   treating a self-issued sandbox claim as proof?
2. Should a future remote transport use mutual TLS-bound one-time grants or a
   provider-attested receipt model?
3. Which streaming and tool-call shapes belong in a later model-route contract
   rather than this governance-focused profile?
