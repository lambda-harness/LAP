# LEP-0006: Manifest Profile Declaration

- **Status:** Implemented
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-29`
- **Requires:** LEP-0005
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal adds optional `agent.json.profiles` metadata so an Agent package
can state the versioned LAP Profiles its implementation intends to support.
For a Local external workflow orchestrator, a Host can reject a missing
`lap-workflow/0.1` declaration before a root workflow Run begins, while the
existing per-Run handshake remains the authoritative proof before `run.start`.

## Motivation

LEP-0005 deliberately proves the Workflow Profile at invocation time. That is
the correct safety boundary: a Local Agent may advertise a dependent profile
only when the Host asks for it, so an ordinary activation handshake cannot
authoritatively discover all future profile support. However, without a
declaration a workflow author or Host only learns that a selected package is
incompatible after beginning execution preparation.

Package metadata can provide a useful earlier compatibility signal without
conflating intent with authority. The Host needs both: a declared contract for
discovery and workflow validation, and a live protocol proof before sensitive
workflow context reaches a process.

## Scope and Non-Goals

This proposal defines `agent.json.profiles`, its Local baseline requirement,
and preflight behavior for a Local external workflow orchestrator. It does not
add Agent-to-Agent connections, delegated authorization, credentials, package
trust, new envelope fields, or a replacement for LEP-0005 negotiation. It does
not require A2A or native packages to make a Local Profile declaration.

## Normative Specification

`agent.json` MAY contain `profiles`, a unique array of one to sixty-four
versioned Profile identifiers matching
`^[a-z][a-z0-9-]{1,63}/[0-9]+\\.[0-9]+$`. The field declares intended
implementation support only.

When a package uses `transport.kind: "lap-local"` and declares `profiles`, the
array MUST contain `lap-local/0.1`. A Local package intended for a
`lap-workflow/0.1` `orchestrator` node MUST declare both `lap-local/0.1` and
`lap-workflow/0.1`.

Before accepting a workflow for execution, a Host MUST resolve the selected
Local external orchestrator package and verify those two declarations. A
missing declaration or missing `lap-workflow/0.1` MUST produce `LAP-204`; the
Host MUST NOT start the root workflow Run, send the orchestrator Context Packet,
or create a proposal Run.

The declaration MUST NOT grant dispatch, tenant, approval, credential, or
capability authority. For each Local orchestrator invocation, the Host MUST
still perform LEP-0005's `agent.hello` / `agent.welcome` profile verification
before `run.start`. A live handshake mismatch remains `LAP-204` even when the
manifest declaration is present.

## Security, Tenancy, and Authorization

The declaration narrows accidental context disclosure by allowing a Host to
reject an incompatible package before it prepares a workflow run. It is
untrusted package metadata and cannot elevate a package: the Host continues to
own installation, activation, tenant admission, capability scope, approval,
budget, and dispatch checks. A forged declaration fails closed when the live
Local negotiation does not echo the required profile.

## Privacy and Observability

The declared profile identifiers and a typed `LAP-204` rejection are safe
operator-facing lifecycle facts. Hosts MAY expose them in a package directory
or audit event, but MUST NOT attach Context Packet contents, user input,
credentials, package command paths, or hidden reasoning to a preflight result.

## Compatibility and Migration

The manifest field is additive. Existing packages without `profiles` remain
valid for ordinary compatible runs. This tightens only Local packages selected
as workflow orchestrators: package authors add the two identifiers to their
manifest, then retain LEP-0005's runtime support. Hosts that do not recognize
the field may continue ordinary Local behavior, but cannot claim FLOW-15.

## Conformance Plan

FLOW-15 requires the preflight declaration check and preserves FLOW-14 as a
separate runtime proof. The `workflow-orchestrator-context.json` vector adds a
valid declaration and a no-root-run `LAP-204` negative case. Schema tests prove
the Local baseline and uniqueness rules; reference examples declare the
profiles expected by their runnable implementations.

## Reference Implementation Plan

Lambda Harness parses and exposes declared profiles for an active immutable
release, checks them during workflow validation, and still asks for
`lap-workflow/0.1` on every Local orchestrator Run. Its generated Local worker
and orchestrator packages emit the corresponding manifests.

## Alternatives Considered

Inferring profile support from a generic activation handshake is unsound because
an Agent may legitimately advertise a dependent profile only after the Host
requests it. Treating a capability name as proof has the same weakness.
Replacing LEP-0005 with a manifest flag would trust unverified metadata before
context dispatch. Deferring all feedback until invocation remains safe but
produces a poorer workflow-authoring and deployment experience.

## Open Questions

None for `0.1.0-draft`.

## Resolution Record

- **Decision:** Implemented
- **Decision date:** `2026-08-29`
- **Target release:** `0.1.0-draft`
- **Rationale:** Package-declared intent and per-Run protocol proof solve
  different interoperability problems and must both remain explicit.
- **Required follow-up:** Independent Hosts claiming FLOW-15 publish a
  workflow-validation `LAP-204` test and retain the FLOW-14 no-`run.start`
  negative test.
