# LAP Core Specification

**Version:** `0.1.0-draft`

**Status:** Proposed
**Normative language:** The key words **MUST**, **MUST NOT**, **REQUIRED**,
**SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in
RFC 2119 and RFC 8174 when written in uppercase.

## 1. Scope

LAP defines a managed-agent contract between a **Host Runtime** and an **Agent
Implementation**. The contract supports installation, activation, invocation,
progress reporting, artifacts, cancellation, failure, removal, and supervised
delegation.

LAP does not standardize model prompts, planning algorithms, tool semantics,
storage engines, UI design, scheduler implementation, or hidden model
reasoning. MCP and A2A remain independent interoperability layers.

## 2. Terms

| Term | Definition |
|---|---|
| Agent | A logical, installable capability with a stable `agent_id`. |
| Release | An immutable implementation version of an Agent. |
| Host Runtime | Trusted process that owns identity, policy, state, and dispatch. |
| Adapter | Host component that maps LAP to `native`, `lap-local`, or `a2a`. |
| Run | One execution of one resolved Agent Release. |
| Context Packet | Bounded input, artifact references, limits, and scoped grants for a Run. |
| Artifact | Durable output identified by metadata and an access-controlled reference. |
| Capability Grant | Runtime-issued authority bounded by tenant, run, capability, audience, and expiry. |

## 3. Architectural Boundary

The Host Runtime is authoritative for tenant identity, resolved release,
permissions, child-run creation, budgets, audit retention, and terminal run
state. An Agent Implementation is authoritative only for its declared output
within the run and grants it received.

An orchestrator is an Agent that may propose child dispatches. It does not gain
the ability to bypass the runtime. The runtime MUST reject dispatches that
violate capability policy, depth, concurrency, budget, timeout, tenant, or
cycle constraints.

## 4. Identity and Versioning

`agent_id` MUST be a lowercase reverse-domain-like identifier matching
`^[a-z][a-z0-9.-]{2,127}$`. A release is identified by `(agent_id, version,
integrity_digest)`. A Host Runtime MUST resolve a release before a run starts
and MUST retain that resolution for the run's entire lifetime.

LAP versions use `major.minor` protocol compatibility. A peer MAY negotiate a
higher compatible minor version; a peer MUST reject an unsupported major
version. Profile extensions use reverse-DNS identifiers inside `extensions`.

## 5. Manifest and Package

An Agent Package MUST contain one `agent.json` conforming to
[`schemas/agent-manifest.schema.json`](schemas/agent-manifest.schema.json).
The package MAY contain binaries, libraries, documentation, and profile-specific
assets. A package MUST NOT be activated until its manifest, transport
compatibility, integrity policy, and health check pass.

The required `lap` field declares the package's primary Core version. An Agent
MAY additionally declare `protocol_versions` to advertise compatible versions
for negotiation.

The optional `profiles` field is a unique, versioned declaration of profile
contracts that the package author intends the implementation to support. It is
discovery and preflight metadata, not a capability grant, authorization
decision, or proof that a running process accepted a Profile. When a
`lap-local` package declares `profiles`, the list MUST include
`lap-local/0.1`. A Local package that also intends to serve a Workflow
orchestrator declares `lap-workflow/0.1` alongside that baseline profile.
Packages that omit the optional field remain valid for ordinary compatible
runs, but make no additional profile claim. A Host MAY display or use this
metadata to reject an incompatible workflow before execution; it MUST still
negotiate and verify every profile required by a Local Run before `run.start`.

Manifest permissions are requests, not grants. The Host Runtime MUST make the
authorization decision independently for each installation or run.

When `integrity.sha256` is declared, `integrity.path` is REQUIRED and MUST name
one package-relative regular file other than `agent.json`. The digest is the
lowercase SHA-256 of that file's bytes. A Host MUST reject absolute paths, any
traversal segment, symlinked, missing, unreadable, or mismatched targets during
discovery and again before activation uses the release. This is a file-
consistency check, not an authenticity assertion: a party able to alter both
the target and the manifest can alter both values. `publisher` is provenance
metadata only in 0.1; it is not a signature or a trust grant. A package MAY
omit the complete `integrity` object.

The optional [Package Signing Profile](profiles/package-signing.md) adds an
interoperable publisher-authentication assertion over the canonical full
package content address. Its root `lap-signature.json` sidecar is excluded from
that content address only so it can sign it; the Host MUST bind and recheck the
entire sidecar at activation. A signature NEVER grants permissions, tenant
access, or automatic execution on its own. Hosts that require trusted package
signatures MUST reject missing, unknown, invalid, or mismatched signatures with
`LAP-302`.

### 5.1 Capability Contracts

When present, a capability's `input_schema` and `output_schema` are JSON Schema
Draft 2020-12 schema resources. An omitted or empty schema accepts any JSON
value. The input contract describes the exact `run.start.payload.input` value;
the output contract describes `run.result.payload.output` only when the Agent
claims `status: "succeeded"`.

Capability schemas are untrusted package data. In LAP 0.1 they MUST be
self-contained: `$schema`, when present, MUST be
`https://json-schema.org/draft/2020-12/schema`; `$id` is prohibited; and
`$ref`, `$dynamicRef`, and `$recursiveRef` MUST be local fragment references
beginning with `#`. A Host MUST NOT retrieve a schema through the network,
filesystem, package-relative URI, or another ambient resolver while evaluating
a capability contract. Local `$defs` and fragment references are permitted.

Before creating a local process or remote task, a Host MUST normalize the
selected capability input as JSON and validate it against `input_schema`. An
invalid input is a `LAP-201` rejection and MUST NOT start or resume Agent work.
The normalized capability input is part of idempotency equivalence; a retry key
cannot replay a result for different structured input.

After receiving a purported successful terminal result, the Host MUST validate
`output` against `output_schema` before exposing, caching, binding into a
workflow, or recording it as successful. A violation is a `LAP-101` protocol
failure: the Host MUST record a failed terminal outcome and MUST NOT retain the
purported success. Failed, cancelled, and timed-out Agent results are governed
by their typed `error` object and do not require successful-output validation.

## 6. Envelope

Every transport profile serializes the Core Envelope defined by
[`schemas/envelope.schema.json`](schemas/envelope.schema.json).

```json
{
  "lap": "0.1",
  "id": "msg_01J...",
  "producer": "host.runtime",
  "seq": 12,
  "type": "run.start",
  "run": {
    "tenant_id": "tenant_acme",
    "session_id": "session_01J...",
    "run_id": "run_01J...",
    "parent_run_id": "run_01J...",
    "trace_id": "trace_01J..."
  },
  "idempotency_key": "0f33...",
  "payload": {},
  "extensions": {}
}
```

`id` MUST be unique for the producer lifetime. `producer` and `seq` identify
an ordered producer stream; `seq` MUST strictly increase. Consumers MUST
ignore a duplicate `(producer, seq)` and MUST report an out-of-order gap
without inventing missing work.

`tenant_id` is set by the authenticated Host Runtime. An Agent MUST echo it
unchanged in run-scoped output; the Host MUST treat any conflicting value as a
protocol violation and MUST NOT use agent-supplied tenancy for authorization.

## 7. Core Message Types

| Type | Sender | Required meaning |
|---|---|---|
| `agent.hello` | Host | Begin negotiation and identify supported profiles. |
| `agent.welcome` | Agent | Select one compatible version/profile and report readiness. |
| `run.start` | Host | Request one idempotent execution with a Context Packet. |
| `run.accepted` | Agent | Confirm responsibility for the run or return a typed rejection. |
| `run.progress` | Agent | Report an observable non-terminal phase or operation. |
| `run.artifact` | Agent | Report a created artifact reference and metadata. |
| `run.result` | Agent | Publish the one terminal outcome. |
| `run.cancel` | Host | Request best-effort cancellation of a running run. |
| `agent.shutdown` | Host | Request graceful process shutdown. |

The required terminal `run.result.payload.status` values are `succeeded`,
`failed`, `cancelled`, and `timed_out`. A terminal result MUST contain a concise
human-readable `summary`; unsuccessful results MUST additionally contain a
typed `error` object with a stable `code` and operator-readable `message`.

`run.progress` is for observable work such as planning, model call, tool call,
file operation, terminal execution, artifact creation, or approval wait. It
MUST NOT require an Agent to expose private model reasoning.

## 8. Context, Artifacts, and Grants

A Context Packet conforms to
[`schemas/context-packet.schema.json`](schemas/context-packet.schema.json). It
MAY include task input, approved history summary, structured data, artifact
references, deadline, resource budget, and capability grants. It MUST be
bounded by the Host Runtime and SHOULD reference large files rather than
duplicate them in messages.

An Artifact reference supplied in a Context Packet is an input artifact. It is
a Host grant for that Run, not evidence that the Agent may discover or open
arbitrary Host resources. An input artifact MUST be tenant-scoped and immutable
for the Run; an output artifact MUST additionally be immutable once included in
a terminal result.

"lap://run/input/<opaque-name>" is the Core URI form for a Host-granted local
input artifact. Such a reference MUST include id, name, media_type, uri, and
the lowercase SHA-256 sha256 of the exact bytes made available to the Agent.
The URI identifies a profile-scoped run resource, not a network location and
not a durable public link. The profile defines how, or whether, the Agent may
resolve it.

The Host MUST include the immutable identity of every granted input artifact,
including its digest, in run.start idempotency equivalence. A retry whose
attachment bytes or grant identity differ from the original request is
non-equivalent input and MUST NOT replay the original Run. A Host MUST NOT
serialize a Host-provided private source path, ambient credential, or unrestricted storage
locator into a Context Packet or LAP-visible audit event. If the selected
profile has not negotiated a safe way to provide an input artifact, the Host
MUST reject the Run with a typed error before dispatch; it MUST NOT silently
omit the artifact or substitute a private path or invented remote URL.

Capability grants are reserved in `0.1`; implementations MAY omit them. When
implemented, a grant MUST be short-lived, audience-bound to one agent release,
scoped to a tenant/run/capability, and revocable. A grant MUST NOT expose the
Host Runtime's broad credentials.

## 9. Lifecycles

### 9.1 Agent Release

```text
discovered -> validating -> ready -> active -> draining -> disabled -> removed
                         \-> failed
```

`active` releases accept new runs. A Host MUST move a release to `draining`
before disable, update, or removal; it MUST reject new runs while allowing
pinned runs to complete, cancel, or time out. A failed candidate MUST NOT
replace an already active release. Historical runs MUST retain their resolved
agent identity after a release is removed.

For a workflow dispatch, a "pinned" release is a Host-private admission
defined by the [Workflow Profile](profiles/workflow.md), not an Agent-provided
token or a field the Host may accept from a Context Packet. That admission is
bound to one tenant, session, root workflow run, and exact release set; a
draining release may serve only a child covered by that root scope.

Restart-time scanning is a conforming baseline. A hot-reload implementation
MUST preserve the same validation, atomic activation, draining, and rollback
semantics. Discovering a binary alone MUST NOT execute it.

### 9.2 Run

```text
queued -> starting -> running -> awaiting_approval -> running
                              -> succeeded | failed | cancelled | timed_out
```

Terminal states are immutable and mutually exclusive. A Host MUST persist a
single terminal state even when transport disconnect, cancellation, timeout,
and agent exit race. The first valid terminal transition wins; later terminal
messages are recorded as protocol anomalies and MUST NOT rewrite history.

## 10. Reliability

A Host MUST make `run.start` idempotent using `idempotency_key`. Replaying a
previous key for equivalent run input MUST return the original run identity and
MUST NOT start duplicate work. Reusing a key with non-equivalent input MUST
fail with a `LAP-2xx` validation error. A Host MUST enforce deadline, concurrency,
maximum delegation depth, child-run count, and resource budget independently of
the Agent.

If an Agent process exits before a terminal result, the Host MUST end the run
as `failed` with `LAP-500` unless it can prove that a valid terminal result was
durably received. A transport reconnect MAY replay events; consumers MUST use
the producer sequence to de-duplicate them.

## 11. Error Model

| Range | Meaning |
|---|---|
| `LAP-1xx` | Version, framing, or schema violation. |
| `LAP-2xx` | Manifest, capability, or input validation failure. |
| `LAP-3xx` | Authorization, tenant, or policy denial. |
| `LAP-4xx` | Deadline, cancellation, quota, or host lifecycle failure. |
| `LAP-5xx` | Agent implementation or unexpected process failure. |

Error messages MUST be actionable but MUST NOT disclose another tenant's data,
secrets, unrestricted filesystem paths, or hidden reasoning.

## 12. Security

The Host Runtime MUST authenticate the caller before assigning `tenant_id`. It
MUST isolate events, context, artifacts, logs, and approvals by tenant. It MUST
validate manifest paths, prohibit path traversal, avoid shell interpolation
when launching local binaries, bound message size and process resources, and
capture stderr separately from protocol stdout.

An Agent MUST NOT self-approve privileged effects. The approval channel is
owned by the Host Runtime; `0.1` reserves the grant model without requiring
delegated authorization to be implemented.

## 13. Extensibility

An extension MUST be declared in the manifest and negotiated during
`agent.hello` / `agent.welcome`. Extension keys MUST use reverse-DNS naming,
for example `io.example.vector-search`. Unknown optional extensions MUST be
ignored; unknown required extensions MUST cause negotiation failure. Extensions
MUST NOT change Core terminal-state, tenant, idempotency, or authorization
semantics.

A profile-defined Context Packet extension is negotiated through the profile
that defines it. A Host that requires such a profile for a particular Run MUST
offer it in `agent.hello`, verify Agent support in `agent.welcome`, and reject
the Run before dispatch when support is absent. The extension remains bounded
data, not a credential or an authority grant.

## 14. Conformance

An implementation may claim `LAP Core 0.1`, `LAP Local 0.1`, `LAP A2A Bridge
0.1`, or `LAP Package Signing 0.1` only after passing the corresponding requirements in
[CONFORMANCE.md](CONFORMANCE.md). A conformance claim MUST identify the
implementation version, profile, and test suite version.
