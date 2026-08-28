# LEP-0002: Scoped Workflow Release Admission

- **Status:** Implemented
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-28`
- **Requires:** None
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal defines a Host-private workflow release admission for
`lap-workflow/0.1`. It lets a workflow that was admitted while an external
Agent Release was active complete its remaining eligible children after that
release begins draining, without allowing a new workflow or another tenant to
reuse the old release.

No Agent-visible field, Context Packet grant, or Core Envelope field is added.
The change tightens Host lifecycle behavior only.

## Motivation

An immutable workflow graph can contain serial and dynamic child nodes. A
simple release snapshot is insufficient when an administrator disables an
external Agent between the first and later node: either the admitted workflow
breaks unexpectedly, or a stale snapshot can be reused to start unrelated
work. Central multi-tenant Hosts need both properties to be explicit.

## Scope and Non-Goals

This proposal covers Host admission of external Agent Releases for one
workflow root. It does not define delegated credentials, cross-Host transfer
of an admission, durable restart recovery of a running root, or a new Agent
wire message. Native Agent execution retains its Host-defined behavior.

## Normative Specification

When a Host starts a workflow that references one or more external Agent
Releases, it MUST resolve the exact release set and atomically issue one
workflow release admission before any child starts. The admission MUST bind:

1. the exact resolved external release objects or immutable identities;
2. the authenticated `tenant_id`;
3. the containing `session_id`; and
4. the root `workflow_run_id`.

The admission is Host-private capability state. It MUST NOT be serialized in a
workflow document, Context Packet, Core Envelope, Agent-visible event, or
audit payload. A Host MAY record a safe, typed rejection fact, but MUST NOT
expose a bearer value usable to reconstruct admission.

When a release is `draining`, a Host MUST admit a child only if the supplied
Host-private admission is live, covers that exact release, has matching tenant
and session, and the child's direct `parent_run_id` equals the bound root run
ID. A new workflow root, a different tenant/session/root, a closed admission,
or a manually fabricated lookalike MUST be rejected before the target Agent
process or remote task starts.

The Host MUST invalidate the admission when the root reaches a terminal state.
Disabling a release MUST prevent new root admissions immediately, while a live
matching admission MAY complete remaining child nodes. Removal continues to
wait for all active child runs and live workflow admissions to drain.

## Security, Tenancy, and Authorization

The admission is an internal Host authority, not delegated authority. An
untrusted Agent never receives it and cannot choose the tenant, root, or
release it covers. Identity matching prevents a workflow in one tenant or
session from using another workflow's draining release. A registry must retain
the exact issued admission record so a structurally similar object or stale
identifier is insufficient.

## Privacy and Observability

No new wire field or user-visible secret is introduced. Hosts SHOULD record a
typed workflow-admission rejection with safe release identity and reason, and
MUST continue to redact package paths, credentials, and private Context Packet
content.

## Compatibility and Migration

This is a behavior-tightening security clarification for Hosts. Existing
Agents require no change because the admission is not part of the LAP exchange.
Hosts that previously allowed a stale pinned release to begin unrelated work
must reject that work. A workflow already admitted under the new rule remains
able to finish its permitted children during release draining.

## Conformance Plan

FLOW-11 requires root-scoped release admission. The portable
`conformance/workflow-release-admission.json` vector names one matching child
and the required rejection scopes. Because the registry capability is Host
private, an implementation MUST supplement the vector with local lifecycle
tests that prove no target Agent starts for those negative cases.

## Reference Implementation Plan

Lambda Harness issues registry-tracked admissions bound to tenant, session,
root run, and exact `LapRelease` objects. Its lifecycle tests cover draining,
cross-scope attempts, fabricated admissions, terminal close, and removal
blocking while a workflow pin exists.

## Alternatives Considered

Using the release object alone is insufficient because it has no root or
tenant scope. Serializing a token to child Agents would turn a Host lifecycle
record into a bearer credential and expose it to untrusted code. Rejecting all
later nodes after disable makes controlled draining impossible for valid
already-started workflows.

## Open Questions

None for `0.1.0-draft`.

## Resolution Record

- **Decision:** Implemented
- **Decision date:** 2026-08-28
- **Target release:** `0.1.0-draft`
- **Rationale:** Preserve deterministic workflow completion while enforcing
  tenant and lifecycle isolation for pluggable external Agents.
- **Required follow-up:** Independent Hosts should include FLOW-11 evidence in
  their conformance reports before making a workflow-profile claim.
