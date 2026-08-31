# Changelog

All notable changes to LAP are documented in this file.

## Unreleased

- Added LEP-0009 and the non-claimable `lap-model-relay/0.1` draft: portable
  route, request, response, idempotency, and rejection contracts for a future
  Host-observed external Local-Agent model relay. It preserves the current
  fail-closed strict-budget behavior until provider relay and egress-isolation
  evidence are implemented.
- Superseded the former repository-owner extension namespace through LEP-0008.
  Current external workflow and inline-input profiles are `0.2`, use only the
  `io.github.lambda-harness.lap.*` keys, and fail legacy workflow packages
  closed before planning context or dispatch.
- Moved the public source identity, JSON Schema `$id` values, and Go SDK module
  to `github.com/lambda-harness/LAP`. Go consumers must update their import
  path before using this draft revision.
- Added dependency-free Node.js Local Worker and external Orchestrator Agent
  references, each covered by public wire tests and a Node.js 22 CI job.
- Added `tools/lap_local_probe.py`, a bounded author-side executable probe for
  any declared Local Agent capability. It verifies public wire invariants and
  declared JSON contracts without installing the package or claiming Host
  conformance.
- Added LEP-0007 and optional activation-time verification for a declared
  Local Workflow Profile. The evidence is tied to an exact validated release,
  fails a non-negotiating candidate with `LAP-204`, and never replaces the
  required per-Run negotiation.
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
  Python, Go, and Rust reference local-Agent exchanges.

## 0.1.0-draft - 2026-08-26

- Established LAP as a managed-agent contract compatible with MCP and A2A.
- Defined Agent Package, Core Envelope, Agent/Run lifecycles, error classes,
  tenant boundary, hot reload, and supervision rules.
- Added `lap-local/0.1`, `lap-a2a-bridge/0.1`, JSON Schemas, conformance
  assertions, and a local echo-agent fixture.
- Added optional `workflow.policy.max_parallel_nodes` so a workflow can
  declare a bounded parallelism cap that the Host may lower but never raise.
> This draft begins the release history.
