# LAP Enhancement Proposals

LAP Enhancement Proposals (LEPs) are the durable public record for changes to
LAP's normative behavior, schemas, profiles, compatibility rules, or security
boundaries.

## Start a Proposal

1. Open a discussion with the [LEP issue form](../.github/ISSUE_TEMPLATE/lep.yml).
2. Copy [LEP-template.md](LEP-template.md) into this directory as
   `LEP-XXXX-short-title.md` and fill every applicable section.
3. Submit the proposal in a pull request. A maintainer assigns the next
   four-digit identifier when the proposal enters formal review.
4. Keep the proposal status current through acceptance, implementation,
   rejection, withdrawal, or supersession.

The proposal is the decision record. The corresponding specification, schema,
profile, example, and conformance changes remain the source of executable
behavior.

## When an LEP Is Required

An LEP is required for a change that affects at least one of these areas:

- a required or forbidden wire behavior, envelope field, error, lifecycle, or
  transport rule;
- a profile, schema, capability, extension boundary, or conformance assertion;
- compatibility, versioning, tenant isolation, authorization, package trust,
  audit, metering, or security behavior;
- a release that removes or changes behavior accepted in a prior LEP.

Editorial corrections and examples that do not change valid behavior can use a
normal pull request. State why no LEP is needed in that pull request.

## Current LEPs

| LEP | Status | Target | Summary |
|---|---|---|---|
| [LEP-0001](LEP-0001-a2a-inline-inputs.md) | Draft | `0.1.0-draft` | Optional, bounded A2A inline input artifact transfer. |
| [LEP-0002](LEP-0002-scoped-workflow-release-admission.md) | Implemented | `0.1.0-draft` | Root-scoped, Host-private admission for draining workflow releases. |
| [LEP-0003](LEP-0003-capability-scoped-orchestrator-dispatch.md) | Implemented | `0.1.0-draft` | Optional per-Agent capability scopes for orchestrator dispatch. |
| [LEP-0004](LEP-0004-portable-orchestrator-context.md) | Implemented | `0.1.0-draft` | Portable Context Packet planning view for external orchestrators. |
| [LEP-0005](LEP-0005-local-workflow-profile-negotiation.md) | Implemented | `0.1.0-draft` | Per-run Local negotiation before an external Agent receives workflow orchestration context. |
| [LEP-0006](LEP-0006-manifest-profile-declaration.md) | Implemented | `0.1.0-draft` | Discoverable package profile declarations with workflow preflight and per-Run proof. |
