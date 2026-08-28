# LAP A2A Bridge Profile

- **Profile:** `lap-a2a-bridge/0.1`
- **Depends on:** [LAP Core 0.1](../SPEC.md) and a negotiated
[A2A](https://a2a-protocol.org/latest/) version.

## 1. Purpose

This profile lets a Host Runtime register a remote A2A agent as a managed LAP
Agent. The bridge preserves A2A as the network interoperability protocol while
normalizing lifecycle, tenant policy, audit, artifacts, and parent/child
lineage for a local or central Lambda Harness runtime.

LAP MUST NOT claim that an arbitrary A2A agent is safe, tenant-aware, or
conformant with LAP governance merely because it has an Agent Card. The bridge
is responsible for admission and policy enforcement at the host boundary.

## 2. Registration

An A2A-backed manifest declares `transport.kind: "a2a"` and an
`agent_card_url`. The Host fetches and validates the Agent Card at registration
time and periodically according to its cache policy. Registration MUST fail if
the advertised A2A version, identity, endpoint, or requested capability cannot
be admitted by local policy.

The Host stores the card digest and negotiated A2A version with the resolved
LAP release. A changed card is a new candidate release; it MUST go through the
same validation, activation, draining, and rollback rules as a local package.

## 3. Mapping

| LAP concept | A2A bridge behavior |
|---|---|
| Agent identity | Stable local `agent_id` maps to the admitted Agent Card identity. |
| `run.start` | Bridge submits a task/message using the negotiated A2A capability. |
| Context Packet | Bridge maps allowed text, structured data, and artifact references to A2A parts. |
| `run.progress` | Bridge normalizes non-terminal A2A task updates. |
| `run.artifact` | Bridge registers returned A2A artifacts in the Host artifact store. |
| `run.result` | Bridge maps the A2A terminal task outcome to one LAP terminal result. |
| `run.cancel` | Bridge requests cancellation only when the negotiated A2A capability supports it. |

Unknown A2A events MAY be retained as namespaced diagnostic extensions, but
MUST NOT alter LAP terminal state or bypass policy.

### 3.1 Capability Contract Mapping

The Host validates the selected LAP capability input before creating an A2A
task, and validates a normalized successful A2A result against the LAP output
contract before it becomes a successful LAP result. The remote Agent Card does
not replace those checks.

When the admitted A2A Skill declares `application/json` input, the bridge MUST
send the exact normalized LAP capability input as one A2A `data` part. It MAY
send a separate text part for the human-readable task and Host-approved
context. When the admitted Skill accepts only `text/plain`, the bridge MUST
include the exact canonical JSON value in a clearly labeled text part; it MUST
NOT flatten, silently omit, or transform structured fields to make a remote
submission succeed. This text fallback preserves data but does not claim that
an arbitrary remote Agent has independently validated the LAP contract.

An invalid LAP input is rejected with `LAP-201` before the bridge submits or
resumes a task. An A2A result that fails the declared LAP output schema is a
`LAP-101` failure and MUST NOT be exposed, cached, or used as a successful
workflow node output.

## 4. Identity and Authorization

The bridge authenticates to the remote agent using a Host-approved mechanism.
It MUST NOT forward a caller's broad credentials by default. If delegated
credentials are introduced later, they MUST satisfy LAP Core grant constraints
and be explicitly permitted by tenant policy.

The Host Runtime remains the authority for `tenant_id`, resource budget,
approval, artifact access, and audit retention. A remote agent's claimed
tenant, capability, or terminal state is input to validate, not authority to
trust.

## 5. Input Artifact Transfer

The base `lap-a2a-bridge/0.1` profile does not define binary attachment transfer.
A Core input artifact with a "lap://run/input/..." URI is local to a Host Run
and MUST NOT be forwarded as a local path, guessed public URL, or an
unverified A2A part.

The optional [A2A Inline Inputs Profile](a2a-inline-inputs.md) defines a
bounded `FilePart.bytes` mapping for a small, explicitly approved input file.
It is the only attachment-transfer profile defined for LAP 0.1. A Host MUST
not infer it from ordinary A2A file support or an Agent Card alone.

If a Run has one or more input artifacts and the Inline Inputs Profile is not
admitted by every required gate, the bridge MUST reject the Run with a typed
`LAP-402` error before creating or resuming a remote task. It MUST NOT silently
drop the artifacts merely to submit the textual task.

Remote URL/file retrieval, transfer of output artifacts back to the Host,
remote retention/deletion attestations, and large-file staging require a
separate future profile. That profile MUST declare its direction,
authenticated sender and receiver, tenant/run binding, maximum size and count,
SHA-256 verification, retention/deletion behavior, audit fields, and
idempotency effects.

## 6. Failure and Recovery

If an A2A stream disconnects, the bridge SHOULD resubscribe or retrieve task
state when supported by the negotiated A2A version. It MUST de-duplicate
replayed updates before producing LAP events. If it cannot establish a valid
terminal outcome before the LAP deadline, it MUST complete the LAP run as
`failed` or `timed_out` with a typed error and retain the remote task reference
for operators.
