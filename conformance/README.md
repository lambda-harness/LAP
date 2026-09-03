# LAP Conformance Kit

This directory contains stable, machine-readable material for interoperable
LAP 0.1 checks. It is deliberately small: the kit verifies the public wire
contract, while each Host still proves its own policy, storage, isolation, and
supervision behavior with implementation-local tests.

## What Is Portable

`local-stdio-roundtrip.json` is a canonical `lap-local/0.1` exchange. It
contains Host frames and the expected Agent message sequence for a successful
run. A compatible local Agent can be tested by supplying its executable with
the same Host frames and verifying the invariant fields documented in the
vector. Its Context Packet includes a digest-identified
lap://run/input/... artifact reference; the vector verifies the public
reference shape, not a Host's private staging directory.

The repository test suite validates the vector against the Core schemas and
runs the Python, Go, and Rust reference echo Agents with it. This catches
protocol drift in a form that an independent Host or Agent author can
reproduce.

`tools/lap_local_probe.py` lets an Agent author exercise the package's declared
`lap-local` command directly. It adapts the public Host frame shape to one
selected declared capability and JSON input, then validates the successful
handshake, ordered Agent frames, run identity, terminal result, and declared
output contract. It never installs the package or grants it authority, and its
machine-readable report deliberately excludes raw input, Agent output, command
arguments, and package paths. The probe is evidence for an Agent
implementation, not a Host conformance certification.

`host-metering.json` is a deterministic `lap-host-metering/0.1` arithmetic
vector. It covers a worst-case reservation, provider-reported cached usage,
and the required full-reservation fallback when usage is absent. It does not
prove a Host's private provider integration or pricing calibration; those are
implementation-local conformance obligations.

`model-relay.json` is a draft `lap-model-relay/0.1` governance vector. It
fixes the Local profile negotiation, bounded route context, request/response
payload shapes, idempotent replay, and pre-provider rejection conditions. It
does not make the profile claimable: the published Core does not yet register
the relay frame types, and a real Host still needs provider-adapter and
deployment-isolation evidence.

`tools/lap_model_relay_probe.py` drives the published Python relay reference
through a deterministic stdin/stdout exchange. It validates the draft profile
handshake, route context, idempotency key, correlated response, and terminal
output contract without contacting a provider. It is Agent-side draft evidence,
not a Host metering or sandbox certification.

`workflow-release-admission.json` defines the host-private root scope for a
draining external release: exact tenant, session, root run, and release set.
It names the matching child that may continue and the cross-scope, closed, and
fabricated-admission cases that must start no target Agent. The admission token
itself is deliberately absent from every LAP envelope; implementations prove
the private registry behavior with local lifecycle tests.

`workflow-capability-scopes.json` defines a capability-scoped dynamic dispatch
for `lap-workflow/0.2`. It distinguishes one accepted Agent-and-capability
pair from an Agent outside the immutable allowlist, a capability declared by
the Agent but absent from its scope, and an undeclared capability. Every
rejection starts no target Agent. It also carries missing and extra scope-key
documents that require semantic validation beyond JSON Schema alone.

`workflow-orchestrator-context.json` defines the exact Context Packet extension
that a Host supplies to an external `orchestrator` node. It proves the stable,
sorted Agent-and-capability planning view, its reusable dispatch-output schema,
and the separate A2A JSON data-part mapping. It also names the private-field,
scope, and missing-A2A-JSON-input failures that must occur before an external
task or target Agent starts. For a Local external orchestrator it records the
`agent.json.profiles` preflight declaration, an optional activation probe for a
Host claiming `FLOW-16`, and the separate live `agent.hello` / `agent.welcome`
proof. A missing Workflow Profile fails with `LAP-204` before work starts; a
failed activation probe leaves the candidate release inactive and unverified,
while every invocation still requires the live proof.

`a2a-inline-inputs.json` is a deterministic `lap-a2a-inline-inputs/0.2`
admission vector. It proves the manifest opt-in, Host-policy, and selected
Skill MIME gates; the exact A2A `FilePart.bytes` mapping; and safe metadata.
It intentionally cannot prove a remote Agent's retention or deletion behavior;
that remains an administrator trust decision, not a conformance claim.

## What A Claim Must Include

A conformance claim is a JSON document conforming to
[`../schemas/conformance-report.schema.json`](../schemas/conformance-report.schema.json).
It identifies the implementation, version, profiles, exact command, suite
version, execution time, and result for every claimed assertion.

The report is evidence, not a self-issued certification. `not_applicable` is
valid only for an assertion outside the claimed profiles. A `passed` assertion
must include a concise reproducible evidence reference.

## Run The Published Checks

```bash
python -m pip install -e ".[dev]"
python -m pytest

# Run a bounded Agent-side Local wire probe against one package entry point.
python tools/lap_local_probe.py --package /path/to/my-agent \
  --capability task.run \
  --input '{"task":"verify the release"}'
```

The test command validates all published examples, schemas, report example,
and the Python local round trip. When Go and Rust are available, it also
drives those reference Agents with the same vector; the public CI guarantees
all three paths. Hosts should add their implementation-specific
coverage for lifecycle races, tenant isolation, policy, and storage recovery
before claiming those rows in `CONFORMANCE.md`.
