# LAP: Lattice Agent Protocol

- **Status:** `0.1.0-draft`
- **License:** Apache-2.0
- **Tagline:** Orchestrate Any Agent. Connect Everything.

LAP is an open, managed-agent interoperability specification. It makes an
agent package, a local executable, a native runtime agent, or a remote agent
look like the same supervised unit to a host runtime.

LAP is deliberately narrow. It does **not** replace existing standards:

- [MCP](https://modelcontextprotocol.io/) connects models and agents to tools,
  resources, and prompts.
- [A2A](https://a2a-protocol.org/latest/) connects independent remote agents.
- LAP defines the lifecycle and runtime contract for installable, governed
  agents, including local binaries and A2A-backed agents.

## Why LAP

An agent is more than a prompt or a tool. A portable agent needs an identity,
version, declared capabilities, a transport, a health contract, scoped
permissions, observable progress, cancellation, artifacts, and a dependable
terminal result. Without those contracts, "plug-in agents" become arbitrary
process execution with unreliable handoffs.

LAP standardizes that missing boundary.

```text
Agent package -> Registry -> Supervisor -> Adapter -> Agent implementation
                                      |-> policy / approval
                                      |-> events / audit / artifacts
```

## What LAP Covers

| Concern | LAP answer |
|---|---|
| Discover and install | Versioned `agent.json` manifest and package profile. |
| Run a local binary | `lap-local` UTF-8 NDJSON over supervised stdin/stdout. |
| Invoke a remote agent | `lap-a2a-bridge`, using negotiated A2A semantics. |
| Observe work | Ordered progress, artifact, and terminal events. |
| Stop and retry safely | Idempotency keys, deadlines, cancellation, immutable terminal states. |
| Govern a tenant | Runtime-derived tenant identity and scoped capability grants. |
| Compose agents | Parent/child lineage and a workflow profile for a trusted supervisor. |

## Documents

- [Core Specification](SPEC.md): terms, envelope, lifecycle, governance, and
  compatibility rules.
- [Local Stdio Profile](profiles/local-stdio.md): the normative local-process
  transport for a supervised external Agent implementation.
- [A2A Bridge Profile](profiles/a2a-bridge.md): interoperability rules for
  managed remote A2A agents.
- [A2A Inline Inputs Profile](profiles/a2a-inline-inputs.md): optional,
  bounded transfer of explicitly granted small Host input artifacts to an
  admitted A2A Skill using A2A `FilePart.bytes`.
- [Package Signing Profile](profiles/package-signing.md): optional Ed25519
  publisher provenance for portable Agent Packages.
- [Workflow Profile](profiles/workflow.md): user-owned, versioned Agent graphs
  with runtime-enforced dispatch boundaries.
- [Host Metering Profile](profiles/host-metering.md): optional direct-model
  Host accounting for enforceable workflow input and cost budgets.
- [Go Agent SDK](sdk/go/README.md): dependency-free Agent-side helper for the
  Local Profile; it is not a Host Runtime or a conformance certification.
- [Agent Manifest](schemas/agent-manifest.schema.json),
  [Envelope](schemas/envelope.schema.json),
  [Context Packet](schemas/context-packet.schema.json), and
  [Run Result](schemas/run-result.schema.json), and
  [Workflow](schemas/workflow.schema.json), and
  [Package Signature](schemas/package-signature.schema.json) Schemas:
  machine-readable contracts.
- [Conformance Report](schemas/conformance-report.schema.json) Schema: a
  machine-readable record of an implementation's reproducible claim.
- [Conformance](CONFORMANCE.md): required tests and conformance claims.
- [Conformance Kit](conformance/README.md): portable vectors, report example,
  and the exact verification command.
- [Governance](GOVERNANCE.md): versioning and change process.
- [LAP Enhancement Proposals](proposals/README.md): public design records for
  normative, compatibility, and security changes.

## Minimal Local Package

```text
my-agent/
  agent.json
  bin/
    <agent-entrypoint>
  lap-signature.json  # optional, signed publisher provenance
```

The runtime validates the manifest, starts the process, negotiates LAP, and
only then marks the release active. Finding a binary on disk is never
permission to execute it.

See the [echo-agent example](examples/echo-agent/README.md) for a runnable
Python reference conversation, the [echo-agent-go example](examples/echo-agent-go/README.md)
for a Go implementation of the same `lap-local` exchange, the
[echo-agent-rust example](examples/echo-agent-rust/README.md) for a Rust
implementation, and
[release-check.workflow.json](examples/release-check.workflow.json) for a
validated workflow graph.

## Design Principles

1. **Compatibility before replacement.** Reuse A2A and MCP rather than create
   a competing wire protocol for their domains.
2. **Runtime-enforced governance.** An agent may request work; only the host
   runtime may authorize, dispatch, approve, cancel, or finalize it.
3. **Hot reload without ambiguity.** New runs resolve one immutable release;
   old releases drain instead of changing beneath an in-flight task.
4. **Observability without hidden reasoning.** Progress describes real
   operations and outcomes, not private chain-of-thought.
5. **Tenant identity is authoritative.** The authenticated host establishes
   it; an agent cannot select or broaden it.

## Status and Scope

`0.1.0-draft` is intended for design review and reference implementations. It
is not yet a stable compatibility promise. Implementers should report gaps via
issues or a LAP Enhancement Proposal before depending on it in production.

The first conformance target is a local executable integrated by an independent
host in under 30 minutes. The published Python, Go, and Rust references
exercise the same vector so the Local Profile is not coupled to one language
runtime. Remote discovery and delegated authorization are intentionally layered
on top of that target. The workflow graph is specified in this draft; a
production reference executor follows the Local Profile.

## Validate the Draft

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

These checks validate the published schemas, conformance report, portable
round-trip vector, and local echo-agent through a real stdin/stdout protocol
exchange. When Go or Cargo is on `PATH`, the same suite also runs the Go or
Rust reference respectively; the public CI includes a pinned Go 1.21 job for
the Go reference.

## Contributing

Read [GOVERNANCE.md](GOVERNANCE.md). Changes to normative language, schemas, or
profiles require a versioned proposal and conformance impact analysis. Start
with the [LEP template](proposals/LEP-template.md).
