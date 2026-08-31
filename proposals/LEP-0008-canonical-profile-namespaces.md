# LEP-0008: Canonical Profile Namespaces

- **Status:** Implemented
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-31`
- **Requires:** LEP-0001 through LEP-0007
- **Supersedes:** LEP-0001, LEP-0004
- **Superseded by:** None

## Summary

This proposal moves LAP-owned profile extension identifiers from the former
repository-owner namespace to the canonical `lambda-harness` namespace. It
publishes `lap-workflow/0.2` and `lap-a2a-inline-inputs/0.2`, preserving their
existing authority boundaries while making the wire migration explicit.

The LAP Core version remains `0.1`. This is a breaking correction within the
unreleased `0.x` draft, so an external workflow Agent must be rebuilt and
re-activated rather than silently treated as compatible.

## Motivation

LAP's canonical repository and Go module now live at
`github.com/lambda-harness/LAP`, but two profile-owned wire keys still encoded
the former repository owner. A reverse-DNS extension identifier is a protocol
identity, not display text: leaving it behind would make package source,
conformance vectors, SDKs, and Host output disagree about the standard.

Keeping the old workflow key under the same negotiated profile version would
be worse than a visible incompatibility. An older external orchestrator could
negotiate `lap-workflow/0.1`, ignore the replacement Context Packet key, and
only fail after a real dispatch attempt. A new profile version lets the Host
fail the package before it receives planning context or starts a workflow node.

## Scope and Non-Goals

This proposal changes only the ownership namespace and profile revision for:

| Previous draft profile | Canonical profile | Canonical extension key |
|---|---|---|
| `lap-workflow/0.1` | `lap-workflow/0.2` | `io.github.lambda-harness.lap.workflow.orchestrator` |
| `lap-a2a-inline-inputs/0.1` | `lap-a2a-inline-inputs/0.2` | `io.github.lambda-harness.lap.a2a.inline-inputs` |

It does not change Core envelopes, package signing, workflow admission,
capability scopes, approval, deadline, quota, A2A `FilePart` serialization,
artifact authorization, or the meaning of either extension payload. It does
not introduce a dual-key compatibility mode, delegated credentials, or a new
Agent-to-Agent authorization channel.

The workflow admission, capability-scoped dispatch, Local negotiation,
manifest declaration, and activation-evidence rules from LEP-0002, LEP-0003,
and LEP-0005 through LEP-0007 carry forward unchanged under
`lap-workflow/0.2`; this proposal changes their profile identity, not their
authorization or lifecycle semantics.

## Normative Specification

1. The only current draft identifier for the external workflow profile is
   `lap-workflow/0.2`. Its Context Packet extension key is exactly
   `io.github.lambda-harness.lap.workflow.orchestrator`, and its extension
   payload `version` is exactly `"0.2"`.
2. A Host selecting an external `orchestrator` node MUST offer
   `lap-workflow/0.2` in `agent.hello`, verify that exact profile in
   `agent.welcome`, and reject a missing response with `LAP-204` before sending
   the Context Packet or `run.start`.
3. The only current draft identifier for bounded A2A inline inputs is
   `lap-a2a-inline-inputs/0.2`. Its descriptive `FilePart.metadata` key is
   exactly `io.github.lambda-harness.lap.a2a.inline-inputs`. The value shape,
   three admission gates, and no-remote-task-on-rejection behavior remain as
   defined by the profile.
4. A conforming current-draft Host or Agent MUST NOT emit either former
   `io.github.dongrv.lap.*` key. It MUST NOT send both keys in one Context
   Packet or A2A file part. A Host MUST NOT treat a legacy key as proof that a
   peer supports the corresponding `0.2` profile.
5. The old profile identifiers and keys are historical draft records only.
   They are not current conformance targets and have no downgrade semantics.

The exact current behavior is specified by the revised Workflow and A2A Inline
Inputs profiles and their portable conformance vectors.

## Security, Tenancy, and Authorization

The canonical workflow extension remains a bounded planning view, never a
credential or dispatch grant. The Host still resolves releases, validates
tenant admission, capability scopes, approval, budget, depth, deadline, and
cycle policy before starting every child. Refusing a `0.1` workflow peer before
Context Packet delivery avoids accidental exposure of planning data to a peer
that cannot prove the current contract.

The inline-input extension remains descriptive integrity metadata. It neither
grants file access nor replaces the Host policy, manifest opt-in, selected A2A
Skill MIME-mode, digest, size, and request-bound checks. No raw bytes, local
paths, credentials, or tenant identifiers are added to either payload.

## Privacy and Observability

Host audit may record the negotiated canonical profile and extension key as a
safe protocol fact. It MUST NOT record the raw Context Packet, file bytes,
Base64, source paths, secrets, or hidden reasoning. Migration failures are
typed compatibility results and do not require an Agent to reveal its code or
configuration.

## Compatibility and Migration

This is a breaking change in an unreleased `0.x` draft. There is no dual-send
or legacy fallback: two authoritative planning keys would make idempotency and
Agent behavior ambiguous.

1. A Host updates its negotiated profile list, canonical extension constants,
   conformance vector, and audit labels.
2. A workflow Agent updates its manifest and `agent.welcome` profile to
   `lap-workflow/0.2`, reads only the canonical extension key and payload
   version, then is rebuilt, signed if required, and re-activated.
3. An A2A inline-input implementation updates only the canonical metadata key;
   it retains the existing A2A `FilePart.bytes` and three-gate admission rules.
4. An older workflow package fails closed with `LAP-204` before planning
   context or `run.start`; operators must not bypass that result by injecting a
   legacy key.

Previously issued runs retain their recorded release identity and audit data.
New current-draft runs use only the canonical identifiers.

## Conformance Plan

The existing `FLOW-13` through `FLOW-16` vectors and assertions move to
`lap-workflow/0.2` and require the canonical workflow extension key. The
existing `INLINE-01` through `INLINE-03` vector moves to
`lap-a2a-inline-inputs/0.2` and requires the canonical inline-input metadata
key. Negative tests verify that an old workflow profile cannot pass the
per-Run negotiation or receive planning context.

Independent implementations must run the revised public vectors and publish
their own no-dispatch/no-remote-task evidence. A historical 0.1 result is not
a claim for either 0.2 profile.

## Reference Implementation Plan

Lambda Harness updates its Local handshake, workflow runtime, A2A bridge,
source scaffolds, tests, and UI-facing audit facts in the same release. The Go
SDK and Python, Node.js, Go, and Rust reference orchestrators use the canonical
workflow key. This is implementation evidence, not a substitute for the
published profiles and vectors.

## Alternatives Considered

| Alternative | Decision |
|---|---|
| Keep the former namespace indefinitely | Rejected: source identity and wire identity would remain inconsistent. |
| Replace the key under `lap-workflow/0.1` | Rejected: an old Agent could nominally negotiate but silently ignore its planning scope. |
| Send both old and new keys | Rejected: duplicates authority-adjacent input and makes idempotency and precedence ambiguous. |
| Add a new Core protocol version | Rejected: the Core envelope and its security model do not change. |

## Open Questions

None for this draft migration.

## Resolution Record

- **Decision:** Implemented
- **Decision date:** `2026-08-31`
- **Target release:** `0.1.0-draft`
- **Rationale:** A versioned profile migration aligns the canonical public
  source and wire identities while failing outdated workflow peers closed.
- **Required follow-up:** Independent Hosts and Agent SDKs publish revised
  `FLOW` and `INLINE` conformance results before claiming the `0.2` profiles.
