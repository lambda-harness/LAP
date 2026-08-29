# LEP-0007: Activation-Verified Workflow Profile

- **Status:** Implemented
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-29`
- **Requires:** LEP-0005, LEP-0006
- **Supersedes:** None
- **Superseded by:** None

## Summary

This proposal defines optional activation-time verification for a Local package
that declares `lap-workflow/0.1`. A Host that claims the behavior probes the
candidate before activation and records verified support only when the live
Local handshake confirms it. The existing per-Run negotiation remains the
authoritative gate before a workflow Context Packet or `run.start` is sent.

## Motivation

LEP-0006 makes a package's intended profiles discoverable, while LEP-0005
proves a Workflow Profile immediately before an orchestrator invocation. Those
two points leave an operational gap: a deployment may look compatible in a
directory but only discover that its executable cannot negotiate the declared
profile when a workflow later needs it.

Hosts that want stronger deployment feedback need a narrowly scoped way to
exercise the declared dependent profile during activation. The result must be
clearly distinguished from both manifest metadata and a future invocation:
otherwise an implementation could accidentally treat stale lifecycle state as
authorization or skip the per-Run proof.

## Scope and Non-Goals

This proposal defines an optional Local activation probe for the declared
`lap-workflow/0.1` profile, release-bound evidence, and a portable negative
case. It does not add a Core Envelope field, Agent-to-Agent connection,
delegated authorization, credential exchange, package signature, remote
transport rule, or a replacement for LEP-0005 and LEP-0006.

It does not require every Host to probe profiles at activation, require an
ordinary Local worker to support the Workflow Profile, or standardize a Host's
private persistence or user-interface representation of verification state.

## Normative Specification

A Host MAY probe a Local package during explicit activation when its validated
`agent.json.profiles` declares `lap-workflow/0.1`. A Host claiming `FLOW-16`
MUST, for such a candidate:

1. send an activation `agent.hello` offering both `lap-local/0.1` and
   `lap-workflow/0.1`;
2. verify that the matching `agent.welcome` contains both identifiers before
   recording `lap-workflow/0.1` as activation-verified;
3. bind any verification evidence to the exact validated candidate release;
   it MUST NOT be reused for a different installation, reload candidate,
   replacement, or identity;
4. fail the candidate activation with `LAP-204` when the welcome response lacks
   `lap-workflow/0.1`, and MUST NOT make that candidate active or report its
   Workflow Profile as verified; and
5. perform LEP-0005's per-Run negotiation for every Local external
   orchestrator invocation, regardless of prior activation evidence.

An existing unchanged active release retains only its own independently
recorded evidence when a replacement candidate fails. Existing Local
activation failures, including malformed frames and identity mismatches, keep
their established typed failure behavior.

Activation verification does not alter `run.start.payload.input`, create a
Context Packet, or grant dispatch, tenant, approval, capability, budget, or
credential authority. A Host MUST NOT send workflow Context Packet content
during this probe.

## Security, Tenancy, and Authorization

The probe fails closed before a candidate can be made workflow-capable. An
untrusted package cannot obtain planning context merely by declaring a Profile:
it must echo the requested identifier in the live handshake, and the Host
still validates all workflow policy after that. The probe has no tenant or
session input and conveys no caller credentials, approval state, release
admission, or dispatch authority.

Binding evidence to the exact release prevents an activation result for one
binary or manifest from being used after hot reload. Keeping the prior release
separate also preserves safe drain behavior: a rejected candidate cannot erase
or impersonate the active release's independently established state.

## Privacy and Observability

Hosts MAY record and expose the Profile identifier, lifecycle phase, exact
release identity, and typed result. They MUST NOT use an activation probe to
persist or expose Context Packet contents, user inputs, package command paths,
credentials, secrets, or hidden reasoning. A concise `LAP-204` result is
sufficient when the Workflow Profile is absent.

## Compatibility and Migration

The behavior is additive and opt-in for Hosts. Ordinary Local packages and
Hosts that do not claim `FLOW-16` retain LEP-0006 discovery and LEP-0005
per-Run behavior unchanged. A Host that adopts this claim can activate a
workflow-capable Local package only after it already supports the LEP-0005
welcome profile set; package authors need no new manifest field beyond the
LEP-0006 declaration.

The activation result is diagnostic evidence, not a downgrade path. A Host
MUST still reject a particular orchestrator invocation with `LAP-204` if that
Run's live response lacks the Workflow Profile.

## Conformance Plan

`FLOW-16` requires an implementing Host to exercise a declared Local Workflow
Profile during activation, bind successful evidence to the exact release, and
fail a missing workflow response with `LAP-204` before the candidate becomes
active. The portable `workflow-orchestrator-context.json` vector includes the
required manifest/host/verified profile sets and a no-active-release negative
case. Its executable tests verify that the published vector remains exact.

Independent Hosts claiming `FLOW-16` must also publish implementation-local
tests that prove a reload or replacement cannot inherit a prior release's
verification evidence, and that a later invocation still executes `FLOW-14`.

## Reference Implementation Plan

Lambda Harness requests both profiles while activating a Local candidate that
declares `lap-workflow/0.1`. It records the confirmed identifiers on the active
release, clears them for a failed candidate, and continues to request and
verify the same pair on every Local orchestrator Run.

## Alternatives Considered

Treating the manifest declaration as verified would trust mutable package
metadata without asking the executable. Reusing an ordinary Local activation
handshake would not test an optional dependent profile unless the Host offered
it. Treating a one-time activation result as sufficient for every future Run
would allow stale evidence to bypass the only negotiation immediately adjacent
to Context Packet disclosure. Deferring all feedback until a workflow invokes
the package remains safe but gives operators poorer deployment feedback.

## Open Questions

None for `0.1.0-draft`.

## Resolution Record

- **Decision:** Implemented
- **Decision date:** `2026-08-29`
- **Target release:** `0.1.0-draft`
- **Rationale:** Deployment-time evidence catches false workflow-profile
  declarations early while retaining the per-Run handshake as the safety gate.
- **Required follow-up:** Independent Hosts claiming `FLOW-16` publish a
  candidate-replacement isolation test and a separate `FLOW-14` per-Run test.
