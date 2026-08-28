# LEP-0003: Capability-Scoped Orchestrator Dispatch

- **Status:** Draft
- **Type:** Standards Track
- **Target version:** `0.2.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-29`
- **Requires:** None
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal adds an optional, immutable capability scope to an
`orchestrator` node in `lap-workflow`. Today a node restricts a dynamic child
only by `agent_id`; an admitted Agent with multiple declared capabilities can
therefore receive any one of them. The proposed scope lets a workflow author
narrow each allowed Agent to a named set of capabilities while preserving the
existing Agent-ID-only behavior for unmodified workflows.

The change is limited to Host-side dispatch validation. It does not delegate
credentials, alter Agent-to-Agent envelopes, or grant an Agent authority to
expand the workflow's capability policy.

## Motivation

The Workflow Profile permits a designated Agent to propose dynamic children.
The Host already validates that the proposed Agent ID is allowed and that the
resolved release declares the proposed capability. That is sufficient for a
workflow that intentionally trusts every capability of an allowed Agent, but
it is too broad for a user-owned workflow that needs one narrowly defined
operation from an otherwise multi-purpose Agent.

An instruction in an orchestrator prompt is not an authorization boundary:
the Host must enforce the permitted Agent-and-capability pairs before a child
starts. A portable workflow field is needed so authors and independent Hosts
can express and verify that least-privilege boundary consistently.

## Scope and Non-Goals

This LEP proposes an optional `allowed_capabilities` field on an
`orchestrator` node and the corresponding pre-dispatch validation rule. It
does not change static `agent` nodes, Agent manifests, capability input
contracts, workflow release admission, approval policy, delegated grants, or
cross-Host routing. A dynamic child remains a normal Agent invocation under
the existing Workflow Profile rule and cannot recursively gain dispatch
authority in the same root run.

## Normative Specification

For `lap-workflow/0.2`, an `orchestrator` node MAY declare
`allowed_capabilities` alongside its required `allowed_agent_ids`:

```json
{
  "id": "route",
  "type": "orchestrator",
  "agent": { "id": "com.example.planner", "capability": "plan.dispatch" },
  "allowed_agent_ids": [
    "com.example.inspector",
    "com.example.publisher"
  ],
  "allowed_capabilities": {
    "com.example.inspector": ["repo.inspect"],
    "com.example.publisher": ["report.publish"]
  }
}
```

The schema delta is an optional object property with these constraints:

```json
{
  "allowed_capabilities": {
    "type": "object",
    "minProperties": 1,
    "propertyNames": {
      "pattern": "^[a-z][a-z0-9.-]{2,127}$"
    },
    "additionalProperties": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "type": "string",
        "pattern": "^[a-z][a-z0-9._-]{2,127}$"
      }
    }
  }
}
```

When `allowed_capabilities` is present, semantic validation MUST require its
key set to equal the set of `allowed_agent_ids` exactly. A missing Agent ID,
an extra Agent ID, an empty capability list, or a duplicate capability is a
workflow-document validation failure. The mapping is immutable for the
published workflow version and is evaluated against the exact resolved
release for the root run.

Before starting a proposed child, a Host MUST validate all existing Workflow
Profile requirements and, when the mapping is present, MUST also verify that
the proposed `capability` appears in the list for its proposed `agent_id`.
A mismatch is a policy denial in the `LAP-3xx` range, MUST emit a safe typed
dispatch-rejection fact, and MUST NOT start the target Agent.

When `allowed_capabilities` is absent, the Host MUST retain the
`lap-workflow/0.1` Agent-ID-only dispatch behavior. The field narrows
authority only; it MUST NOT make an Agent outside `allowed_agent_ids`
eligible or bypass release admission, tenant isolation, capability
declaration, deadline, quota, depth, cycle, concurrency, or approval checks.

## Security, Tenancy, and Authorization

The scope is workflow configuration, not a bearer credential or delegated
grant. A Host remains the sole authority that resolves the release, evaluates
the authenticated tenant, and decides whether a proposed child may start. An
untrusted orchestrator can request a capability outside the mapping, but it
cannot cause execution because the Host rejects it before process launch or
remote task creation.

The exact-key rule prevents a workflow author from accidentally providing a
scope for only part of a broader Agent allowlist. The field cannot expand the
workflow's authority: an allowed capability still requires the resolved
release to declare it and remains subject to Host policy and human approval.
Hosts MUST isolate rejection facts by tenant and MUST NOT expose private
release metadata, credentials, prompts, or hidden reasoning in an error.

## Privacy and Observability

Hosts SHOULD record a typed `workflow.dispatch_rejected` audit fact for a
scope mismatch with the safe workflow node ID, proposed Agent ID, proposed
capability, and policy reason. The event MUST NOT contain a Context Packet,
input payload, secret, or model reasoning. A successful child continues to
use the existing run, artifact, and terminal-event observability model; this
LEP adds no Agent-visible envelope field.

## Compatibility and Migration

This is an additive, authority-narrowing profile change. Existing `0.1`
workflow documents omit the field and retain their current behavior. A
workflow document that uses `allowed_capabilities` targets `lap-workflow/0.2`
and MUST be rejected by a Host that does not advertise support for that
profile; a Host MUST NOT silently ignore the field or downgrade it to an
Agent-ID-only check.

Authors can migrate incrementally by retaining `allowed_agent_ids`, adding
one scope entry for every listed Agent, publishing a new immutable version,
and then verifying the scoped document with the target Host's conformance
report. In-flight `0.1` roots remain pinned to their admitted graph and are
not rewritten.

## Conformance Plan

This proposal would add `FLOW-12` with portable positive and negative
vectors:

1. A mapped Agent-and-capability pair is eligible when all existing checks
   pass.
2. A capability declared by the Agent but absent from its mapped scope is
   rejected before the target starts.
3. A mapping with missing or extra Agent keys is rejected during document
   validation.
4. An otherwise identical `0.1` document without the mapping retains the
   established Agent-ID-only behavior.

The schema change, profile text, and conformance vector are intentionally not
published by this Draft. They are required before the LEP can move to
`Implemented` status.

## Reference Implementation Plan

After acceptance, a reference Host will add the `0.2` schema and semantic
validator, enforce the mapping in the dynamic-dispatch adapter before child
creation, and publish `FLOW-12` evidence. Until then, implementations MAY
render the proposed mapping for authoring feedback but MUST NOT claim
`lap-workflow/0.2` conformance or represent the behavior as an accepted LAP
standard.

## Alternatives Considered

Keeping only `allowed_agent_ids` is simpler but grants every declared
capability of a selected Agent. Prompt-only restrictions improve guidance but
are not enforceable authorization. Replacing the allowlist with a new array
of Agent-and-capability objects would be expressive, but would duplicate the
existing field and make incremental migration less clear. Delegating a scoped
credential to the orchestrator would create a larger security and lifecycle
surface than this Host-enforced workflow constraint.

## Open Questions

1. Should a future workflow-profile minor version replace the parallel
   `allowed_agent_ids` and `allowed_capabilities` fields with one canonical
   dispatch-target array after a deprecation period?
2. Should the standardized rejection fact reserve a stable symbolic reason in
   addition to its existing `LAP-3xx` class?

## Resolution Record

- **Decision:** Pending
- **Decision date:** Not applicable
- **Target release:** Not applicable
- **Rationale:** Pending public review.
- **Required follow-up:** Resolve open questions, publish the profile/schema
  delta and FLOW-12 vectors, then collect independent implementation evidence.
