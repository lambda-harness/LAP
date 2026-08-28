# Changelog

All notable changes to LAP are documented in this file.

## Unreleased

- Added LEP-0002 and the `lap-workflow/0.1` root-scoped workflow release
  admission rule. A draining external release can complete only children of a
  Host-issued tenant/session/root-bound admission; no Agent-visible token or
  wire-schema field was added.
- Corrected the conformance-report schema so reports can represent every
  published assertion family and profile: `CORE`, `LOCAL`, `A2A`, `INLINE`,
  `SIGN`, `FLOW`, and `METER`.
- Added draft `lap-a2a-inline-inputs/0.1`, a three-gate, bounded A2A
  `FilePart.bytes` input-artifact profile with a portable conformance vector
  and LEP-0001. It is opt-in and does not authorize remote URL retrieval or
  make an unverifiable retention/deletion promise.
- Clarified that LAP expands to **Lattice Agent Protocol**. Existing protocol,
  profile, package, and wire identifiers remain unchanged.
- Added a public LAP Enhancement Proposal lifecycle, issue form, and proposal
  template. Normative changes now have a durable version, compatibility,
  security, and conformance record.
- Added the optional `lap-host-metering/0.1` profile for Host-direct model
  adapters. It defines conservative preflight input/cost reservations,
  provider-usage settlement, integer pricing, and strict non-applicability to
  external or unshared nested Agent execution.
- Added a portable `lap-local/0.1` round-trip vector, machine-readable
  conformance-report schema and example, and executable contract checks.
- Added a dependency-free Go local-Agent reference that passes the same public
  round-trip vector and can be compiled as a Windows executable.
- Added a dependency-free Go Agent-side SDK for `lap-local/0.1`, with real
  stdio tests for negotiation, observable events, cancellation, concurrency,
  terminal-result uniqueness, and graceful shutdown.
- Defined `integrity.path` as the package-relative target of an optional
  `integrity.sha256` file digest; the file-consistency scope and non-signature
  publisher metadata are explicit.
- Added GitHub Actions verification for the published schemas, examples, and
  Python and Go reference local-Agent exchanges.

## 0.1.0-draft - 2026-08-26

- Established LAP as a managed-agent contract compatible with MCP and A2A.
- Defined Agent Package, Core Envelope, Agent/Run lifecycles, error classes,
  tenant boundary, hot reload, and supervision rules.
- Added `lap-local/0.1`, `lap-a2a-bridge/0.1`, JSON Schemas, conformance
  assertions, and a local echo-agent fixture.
- Added optional `workflow.policy.max_parallel_nodes` so a workflow can
  declare a bounded parallelism cap that the Host may lower but never raise.
> This draft begins the release history.
