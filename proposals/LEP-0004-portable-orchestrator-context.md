# LEP-0004: Portable Orchestrator Context

- **Status:** Superseded
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-29`
- **Requires:** LEP-0003
- **Supersedes:** None
- **Superseded by:** LEP-0008

## Summary

This proposal defines a profile-owned Context Packet extension for an external
Agent that serves as a `lap-workflow/0.1` `orchestrator` node. The extension
contains the exact, immutable Agent-and-capability pairs that the Host may
dispatch for that node, so a packaged executable does not have to infer its
authority from a Host-specific natural-language prompt.

The extension is information for proposal construction, not delegated
authority. The Agent returns a JSON dispatch proposal; the Host independently
validates and executes every accepted child under the existing Workflow
Profile.

## Motivation

The Workflow Profile already defines a portable terminal dispatch shape and
requires Host enforcement. An external Agent can therefore return a valid
proposal, but before this change it receives the allowed targets only through
an implementation-specific rendered prompt. That makes independently authored
local executables and bridged remote Agents brittle: they cannot reliably
discover the exact scope, nor can a test fixture distinguish a stable protocol
input from prose decoration.

A Context Packet is the existing bounded, Agent-visible input channel. Adding
a narrow profile extension there preserves the Host's authority while giving
an external orchestrator a machine-readable planning surface.

## Scope and Non-Goals

This LEP adds one `lap-workflow/0.1` Context Packet extension, its schema, a
reusable dispatch-output schema, and conformance material. It applies only to
an external Agent selected by an `orchestrator` node.

It does not add Agent-to-Agent networking, a bearer credential, delegated
approval, direct child-process creation, workflow mutation, arbitrary Host
resource access, a new Core envelope type, or recursive orchestration. It
does not make a proposed dispatch accepted automatically.

## Normative Specification

For an external `orchestrator` node, the Host MUST add the following member to
`run.start.payload.context.extensions`:

```json
{
  "io.github.dongrv.lap.workflow.orchestrator": {
    "version": "0.1",
    "allowed_dispatches": [
      {
        "agent_id": "com.example.inspector",
        "capabilities": ["repo.inspect"]
      },
      {
        "agent_id": "com.example.publisher",
        "capabilities": ["report.publish"]
      }
    ]
  }
}
```

The extension value MUST conform to
[`schemas/workflow-orchestrator-context.schema.json`](../schemas/workflow-orchestrator-context.schema.json).
The `allowed_dispatches` array MUST contain exactly one entry for every
`allowed_agent_ids` member, in ascending `agent_id` order. Each entry's
`capabilities` array MUST be lexicographically ordered and contain exactly the
capabilities that the Host will accept for that Agent: the immutable
`allowed_capabilities` value when present, otherwise the resolved Agent
Release's declared capabilities at root admission time.

The Host MUST construct the extension after it resolves the workflow's Agent
catalog and MUST include the complete extension value in idempotency
equivalence. `run.start.payload.input` remains the selected capability's
ordinary normalized input; the extension MUST NOT be substituted for, merged
into, or used to relax that contract.

An orchestrator Agent's successful output MUST conform to
[`schemas/workflow-orchestrator-output.schema.json`](../schemas/workflow-orchestrator-output.schema.json)
before the Host evaluates the proposal. The output schema establishes syntax
only. The Host MUST still apply the Workflow Profile's allowlist, capability,
scope, release, tenant, deadline, depth, quota, approval, and cycle checks to
every proposal. A rejected proposal remains a typed Host decision and MUST NOT
start the target Agent.

For a bridged A2A Agent, the Host MUST preserve the same extension as a
separate A2A `data` part whose value is an object keyed by
`io.github.dongrv.lap.workflow.orchestrator`. The ordinary normalized
capability input remains its own unchanged A2A data part. Because this profile
requires a machine-readable mapping, a bridged external Agent used as an
orchestrator MUST declare `application/json` input support for the selected
A2A Skill; otherwise the Host MUST reject that node with `LAP-204` before
creating a remote task.

## Security, Tenancy, and Authorization

The extension exposes only the already-authorized stable Agent IDs and
capability IDs. It MUST NOT contain tenant IDs, session IDs, run IDs, release
keys, package paths, artifact locators, prompts, hidden reasoning, credentials,
approval decisions, or mutable budget balances.

The extension does not grant authority. An Agent cannot add a target, widen a
capability list, self-approve an effect, or call a child directly by returning
different JSON. The Host owns release resolution, tenant admission, approval,
budget reservation, child creation, and audit retention. A malformed extension
or unavailable A2A structured-input path is rejected before the external task
starts.

## Privacy and Observability

The extension is an input contract, not an audit payload. Hosts MAY record a
safe fact that an external orchestrator context was supplied, but MUST NOT log
its raw Context Packet together with user input or private execution metadata.
Existing `workflow_dispatch_accepted` and `workflow_dispatch_rejected` facts
remain the observable record of actual Host decisions.

## Compatibility and Migration

This is additive for ordinary Agent nodes and for native orchestrators. Hosts
that implement external orchestrator support add the extension only to an
external `orchestrator` invocation. Existing external Agents can continue as
ordinary `agent` nodes unchanged.

An Agent author migrates by reading the named extension when present and by
returning the published output object. A bridged A2A author must additionally
declare `application/json` for the selected Skill. A Host MUST fail closed for
an A2A orchestrator without that input mode rather than flattening the context
into an ambiguous text-only request.

## Conformance Plan

`FLOW-13` adds a portable vector containing a scoped workflow node, its exact
sorted Context Packet extension, the required external-Agent output, malformed
extension/output cases, and the A2A data-part mapping. Implementations must
validate both published schemas, include the extension in idempotency
equivalence, and prove locally that scope rejection still starts no target
Agent.

## Reference Implementation

[Lambda Harness](https://github.com/dongrv/lambda/commit/cb96c19) is the
initial reference Host for `FLOW-13`. It constructs the extension from the
immutable, admitted workflow definition; canonically includes it in the
external-run idempotency fingerprint; and forwards it without changing the
ordinary capability input.

- Its LAP Local transport places the extension in
  `run.start.payload.context.extensions` and protects the Host-owned Skill
  extension namespace from overwrite.
- Its A2A bridge sends the ordinary capability input and the orchestration
  context as separate `application/json` data parts. A selected remote Skill
  without JSON input support fails with `LAP-204` before remote task creation.
- Its workflow runtime continues to validate every returned proposal against
  the immutable allowlist and optional capability scope before target support
  checks or child creation. It records only a safe summary that the planning
  context was fixed, never the raw Context Packet.

The reference suite covers local delivery, idempotency divergence when only
the extension changes, separate A2A data-part mapping, pre-task A2A rejection,
external-workflow context construction, out-of-scope no-target-start behavior,
and frontend audit rendering. This is reference-Host evidence, not an
independent interoperability claim. Another Host claiming `FLOW-13` MUST run
the published vector and provide equivalent local evidence.

## Alternatives Considered

Keeping a prompt-only target list leaves external executable authors dependent
on undocumented prose and makes conformance impossible to reproduce. Placing
the targets in the capability input would alter user-owned input schemas and
break existing capabilities. Delegating a child-run credential would create a
larger authorization and revocation surface. A Context Packet extension is the
smallest existing protocol surface that conveys planning information without
granting execution authority.

## Open Questions

None for `0.1.0-draft`. A future profile may add an explicitly negotiated
cross-Host delegation grant, but it must not reinterpret this informational
extension as a credential.

## Resolution Record

- **Decision:** Superseded
- **Decision date:** 2026-08-31
- **Target release:** `0.1.0-draft`
- **Rationale:** The bounded, deterministic Context Packet design remains;
  LEP-0008 republishes it under the canonical `lambda-harness` extension
  namespace and an explicitly negotiated `lap-workflow/0.2` profile.
- **Required follow-up:** Independent Hosts should publish the revised
  `FLOW-13` vector results and local no-target-start evidence before claiming
  `lap-workflow/0.2` conformance.
