# Core 0.2 Contract Gate Reference

## Status

Executable reference semantics. This module is not a Core 0.2 Host adapter,
does not make Core 0.2 claimable, and does not implement RFC 8785
canonicalization, package hashing, signature verification, peer authentication,
a trusted release registry, durable activation audit, or context transport.

The reference implementation is
[`src/lap_protocol/contract_gate.py`](../src/lap_protocol/contract_gate.py).
Its executable evidence is
[`tests/test_core_02_contract_gate.py`](../tests/test_core_02_contract_gate.py).

## Scope

`ReleaseIdentity` validates a schema-shaped immutable Core 0.2 release value:

- `agent_id`, version, package digest, and manifest digest;
- a non-empty, unique, canonical-order capability-ID to contract-digest set;
- lowercase `sha256:` digest encoding; and
- a defensive mapping copy when callers need a wire-shaped value.

`ContractGate` takes one already Host-admitted identity and compares every
component of a running Agent identity. A difference returns safe `LAP-103`
without echoing the expected or actual identity values. Malformed identity or
unsafe gate arguments return `LAP-201` before comparison.

`admit()` accepts a zero-argument context supplier instead of a ready-made
context value. It calls that supplier only after exact comparison succeeds. A
Host can therefore avoid constructing, reading, or sending input-artifact
references, credentials, grants, or business metadata to a mismatched Agent.

## Required Host Transaction

A production Host must make this ordering part of its authenticated activation
flow, not call it as an isolated helper:

```text
resolve immutable Host-admitted release record
        |
        v
authenticate/negotiated peer and receive its actual release identity
        |
        v
canonicalize and validate identity data against the trusted record
        |
        +--> mismatch: record safe rejection; do not construct context
        |
        v
persist activation acceptance and outgoing-context intent atomically
        |
        v
construct scoped Context Packet and deliver over protected transport
```

The expected identity must come from an immutable Host release record, never
from an Agent-controlled hello, a mutable UI selection, or a human version
string alone. The Host must authenticate the peer before treating its reported
release object as a candidate identity. Context construction, credential
issuance, activation audit, and outbound delivery need durable Host-specific
failure handling that this in-memory reference intentionally does not provide.

## Failure Rules

| Condition | Reference outcome | Host follow-up |
|---|---|---|
| Package, manifest, capability, version, or Agent ID differs | safe `LAP-103` with component names only | Audit safely; send no Context Packet, credential, or input Artifact. |
| Release object is malformed or unsupported | `LAP-201` validation rejection | Reject before peer/session activation; do not fall back to a looser comparison. |
| Context supplier is not callable | `LAP-201` validation rejection | Treat as Host integration/configuration failure; send nothing. |
| Exact identity matches | supplier runs once after admission | Bind delivery to authenticated peer/session and durable activation record. |

## Evidence Boundary

The reference tests exercise C02-CONTRACT-01's no-context-before-match rule.
They do not prove trusted registry provenance, package canonicalization,
signature trust, transport authentication, durable storage, distributed
activation races, credential redaction, or actual network context delivery.
Those Host/runtime tests remain pending in
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json).
