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
runs the reference echo Agent with it. This catches protocol drift in a form
that an independent Host or Agent author can reproduce.

`host-metering.json` is a deterministic `lap-host-metering/0.1` arithmetic
vector. It covers a worst-case reservation, provider-reported cached usage,
and the required full-reservation fallback when usage is absent. It does not
prove a Host's private provider integration or pricing calibration; those are
implementation-local conformance obligations.

`workflow-release-admission.json` defines the host-private root scope for a
draining external release: exact tenant, session, root run, and release set.
It names the matching child that may continue and the cross-scope, closed, and
fabricated-admission cases that must start no target Agent. The admission token
itself is deliberately absent from every LAP envelope; implementations prove
the private registry behavior with local lifecycle tests.

`workflow-capability-scopes.json` defines a capability-scoped dynamic dispatch
for `lap-workflow/0.1`. It distinguishes one accepted Agent-and-capability
pair from an Agent outside the immutable allowlist, a capability declared by
the Agent but absent from its scope, and an undeclared capability. Every
rejection starts no target Agent. It also carries missing and extra scope-key
documents that require semantic validation beyond JSON Schema alone.

`a2a-inline-inputs.json` is a deterministic `lap-a2a-inline-inputs/0.1`
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
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

The test command validates all published examples, schemas, report example,
and the Python local round trip. When Go is available, it also drives the Go
reference with the same vector; the public CI guarantees that path. Hosts
should add their implementation-specific
coverage for lifecycle races, tenant isolation, policy, and storage recovery
before claiming those rows in `CONFORMANCE.md`.
