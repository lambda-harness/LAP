# LEP-0005: Local Workflow Profile Negotiation

- **Status:** Implemented
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-29`
- **Requires:** LEP-0004
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal makes support for `lap-workflow/0.1` explicit when a Local
external Agent is selected as a workflow `orchestrator`. Before sending an
orchestrator `run.start`, the Host requests and verifies the Workflow Profile
alongside the Local Profile. An Agent that only supports ordinary Local runs
cannot accidentally receive the profile-owned orchestration Context Packet.

## Motivation

LEP-0004 standardized the scoped planning input and output for external
orchestrators, but a Local Agent's normal `lap-local/0.1` handshake did not
prove that it understood that extra contract. A generic executable could be
placed in an orchestrator node and receive structured planning scope solely
because its capability name or description looked suitable. That is brittle
for independent implementers and weakens the intended separation between a
worker and a Host-governed planner.

The Local Profile already has a versioned `agent.hello` / `agent.welcome`
exchange. Requiring the dependent profile there is the smallest interoperable
way to make the additional contract observable before any task data is sent.

## Scope and Non-Goals

This proposal covers only a Local external Agent used by a Workflow Profile
`orchestrator` node. It adds no new envelope field, credential, package
permission, Agent-to-Agent connection, recursive dispatch, or delegated
authorization. A2A continues to use its existing JSON-input requirement from
LEP-0004 because its transport negotiates capability through the Agent Card.

## Normative Specification

For a `lap-local` Agent selected by a `lap-workflow/0.1` `orchestrator` node,
the Host MUST include `lap-local/0.1` and `lap-workflow/0.1` in
`agent.hello.payload.profiles`. Before sending `run.start`, it MUST verify that
the Agent's `agent.welcome.payload.profiles` includes both identifiers.

If `lap-workflow/0.1` is absent, the Host MUST fail the orchestrator node with
`LAP-204` and MUST NOT send `run.start`, the workflow Context Packet extension,
or start a proposed child. The check is made for each orchestrator invocation,
not only at package activation. An Agent that supports the profile MAY still be
activated and used for ordinary Local capabilities with only `lap-local/0.1`.

An Agent MAY advertise optional profiles in its welcome set. A Host MUST treat
a profile as required only when it offered and explicitly needs it for that
Run. The workflow Context Packet remains immutable planning data and is never a
capability grant.

## Security, Tenancy, and Authorization

This change narrows information flow before work begins. A generic Local
executable cannot receive the Host's selected Agent/capability planning view
unless it explicitly supports the Workflow Profile. The profile confirmation
does not grant tenant access, child creation, approval, budget authority,
credentials, or Host paths. The Host still validates every proposal against
tenant admission, release state, scope, depth, quota, deadline, and cycle
rules.

## Privacy and Observability

The profile identifiers and a typed rejection code are safe lifecycle facts.
Hosts MAY record that profile negotiation succeeded or failed, but MUST NOT log
the Context Packet, user input, credentials, or hidden reasoning merely to
prove the check.

## Compatibility and Migration

This is behavior-tightening for Local external Agents used specifically as
workflow orchestrators. Ordinary Local Agent activation and ordinary
capability runs remain compatible. An orchestrator author adds
`lap-workflow/0.1` to its welcome profile set; the Go reference SDK exposes
`Config.AdditionalProfiles` and `WorkflowProfile` for this purpose. Because
`0.1.0` remains a draft, Hosts should surface the actionable `LAP-204` failure
rather than silently treating a non-negotiating Agent as a planner.

## Conformance Plan

`FLOW-14` adds the Local profile set and the no-`run.start` `LAP-204` negative
case to `workflow-orchestrator-context.json`. Reference Python and Go
orchestrators prove their welcome frames advertise `lap-workflow/0.1`; an
independent Host must prove it offers, checks, and fails closed before task
dispatch.

## Reference Implementation

[Lambda Harness](https://github.com/dongrv/lambda) requests the extra profile
only on a Local external orchestrator invocation, validates it before
`run.start`, and leaves ordinary Local runs unchanged. Its generated Go,
Python, and Rust orchestrator templates advertise the profile while generated
workers do not. The LAP Go SDK and Go reference orchestrator support the same
declaration.

## Alternatives Considered

Trusting a capability name such as `plan.dispatch` is not enough: names are
declarative metadata and do not prove the executable understands the context
schema. Adding a new manifest authorization flag would conflate package intent
with per-run Host policy. Sending the context and relying on an Agent to fail
would disclose scope before establishing support. Per-run Local negotiation is
already part of the protocol and keeps the additional surface minimal.

## Open Questions

None for `0.1.0-draft`.

## Resolution Record

- **Decision:** Implemented
- **Decision date:** `2026-08-29`
- **Target release:** `0.1.0-draft`
- **Rationale:** A Local orchestrator must prove it understands the Workflow
  Profile before it receives the Host-scoped planning view.
- **Required follow-up:** Independent Hosts claiming `FLOW-14` should publish
  a no-`run.start` negative test alongside the portable vector result.
