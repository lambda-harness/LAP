# LEP-0001: A2A Inline Input Artifacts

- **Status:** Draft
- **Type:** Standards Track
- **Target version:** `0.1.0-draft`
- **Authors:** `@dongrv`
- **Created:** `2026-08-27`
- **Discussion:** [#1](https://github.com/dongrv/LAP/issues/1)
- **Requires:** None
- **Supersedes:** None
- **Superseded by:** None

## Summary

Define the optional `lap-a2a-inline-inputs/0.1` profile. It lets a LAP Host
send a small, explicitly approved input file to a selected remote A2A 0.3
Skill using the standard Base64 `FilePart.bytes` form, with three independent
admission gates and typed pre-dispatch failures.

The proposal changes neither the LAP Core envelope nor A2A. It adds an
opt-in `transport.input_artifact_transfer: "inline"` manifest field, an
independent profile, conformance rows, and a portable vector.

## Motivation

LAP Core deliberately models an uploaded file as a Host-scoped immutable
artifact. The base A2A bridge correctly rejects it because a `lap://` reference
is not a remote file grant. That preserves integrity but blocks an important
legitimate workflow: a user intentionally grants a small workbook, document,
or image to a remote agent that explicitly accepts that media type.

A2A 0.3 already defines `FilePart` with direct Base64 bytes and requires that
the URI form be absent in that case. A LAP profile can reuse that interoperable
form while retaining the Host's approval, tenancy, audit, idempotency, and
network boundaries. The observed fact is A2A's standard byte form; the
assumption is that a configured remote Agent is sufficiently trusted to receive
the approved bytes. This LEP makes that assumption explicit and revocable.

## Scope and Non-Goals

This LEP defines Host-to-remote transfer of a bounded input file. It defines
admission, source revalidation, wire mapping, error behavior, request bounds,
and safe audit fields.

It does not define public URLs, object storage, upload sessions, output-file
download, remote retention/deletion, virus scanning, delegated credentials,
remote-to-remote exchange, or automatic file-type inference. Those require
separate proposals because they introduce materially different authorities and
failure modes.

## Normative Specification

1. The profile identifier is `lap-a2a-inline-inputs/0.1`.
2. A Run with input artifacts MUST pass all three gates before a remote task is
   created or resumed: Host policy enables the profile; the resolved manifest
   declares `transport.input_artifact_transfer: "inline"`; and the selected,
   admitted A2A Skill declares a matching `inputModes` media type.
3. Matching is case-insensitive after stripping media-type parameters. Exact,
   `type/*`, and `*/*` matching MAY be implemented; a Host MUST NOT infer file
   support from a name, description, or generic Agent capability.
4. The Host MUST read only an approved regular non-symlink source, recheck its
   identity/size, verify its SHA-256 over the bytes to send, and preserve the
   artifact identity/digest in Core idempotency equivalence.
5. Each artifact MUST map to an A2A `FilePart` whose `file.bytes` is Base64,
   whose `file.uri` is absent, and whose `name` and `mimeType` come only from
   the approved artifact. The `io.github.dongrv.lap.a2a.inline-inputs`
   metadata value MAY contain only stable id, lowercase SHA-256, and byte size.
6. The Host MUST bound raw content, Base64 expansion, and final serialized
   request size before network dispatch. A size failure is `LAP-401`; malformed
   metadata is `LAP-201`; missing source is `LAP-404`; source mutation is
   `LAP-409`; and a failed admission gate is `LAP-402`.
7. A failure under this profile MUST create no remote task and MUST NOT silently
   remove the artifact to submit a textual fallback.
8. Progress/audit MAY identify a transfer by profile, artifact id, digest,
   media type, count, and size. They MUST NOT include bytes, Base64, local
   paths, `lap://` URIs, remote URLs, tenant ids, session/user tokens, or
   credentials.

The complete normative text is the
[A2A Inline Inputs Profile](../profiles/a2a-inline-inputs.md).

## Security, Tenancy, and Authorization

The authenticated Host remains the only authority that grants an input file,
selects a remote release, determines tenant identity, and initiates network
traffic. A manifest opt-in is necessary but never sufficient: Host policy and
the selected Skill's declared MIME mode are independent gates. A remote Agent
cannot use the profile to browse local paths, obtain a Host credential, assert
another tenant, or turn a `lap://` identifier into a remote URL.

The remote service receives the approved bytes. LAP cannot prove its future
storage, deletion, processors, or onward disclosure. Hosts MUST treat profile
enablement as a release- and route-specific administrator trust decision. The
existing bridge allow-list, transport-security, no-redirect, deadline, and
credential-delegation rules remain mandatory.

## Privacy and Observability

The local Host may persist normal artifact identity and its safe transfer audit
metadata. It must redact byte content and ambient locators from LAP-visible
events. The profile adds no hidden reasoning requirement. A progress event may
say that approved input was verified and sent, with safe count/size metadata;
it must not describe private model reasoning or expose content.

## Compatibility and Migration

The change is additive and default-deny. Existing Hosts continue to return
`LAP-402` for A2A input artifacts. An older Host ignores no field because an
updated manifest is not admissible to it; an updated Host treats an omitted
field as disabled. Releases already pinned to a Run keep their original
manifest and policy decision. Downgrade is an explicit rejection, never a
silent text-only submission.

## Conformance Plan

Add `INLINE-01` through `INLINE-03` and
`conformance/a2a-inline-inputs.json`. The public vector checks schema-valid
manifest opt-in, the three gates, exact bytes/Base64/SHA-256 mapping, URI
absence, safe metadata, and all required pre-dispatch rejection codes.
Independent Hosts must additionally test their own file-race, policy storage,
audit redaction, tenant isolation, and no-network-on-rejection behavior.

## Reference Implementation Plan

Lambda Harness will implement the profile behind disabled-by-default Host
configuration. It will map only exact approved bytes into A2A `FilePart`,
verify request bounds on the serialized JSON-RPC body, and emit a visible
transfer-progress event. This implementation and its tests are evidence only;
they do not define conformance without the profile and vector.

## Alternatives Considered

| Alternative | Decision |
|---|---|
| Continue rejecting every A2A attachment | Safe but prevents an explicitly granted, supported small-file workflow. |
| Convert `lap://` to a local/public URL | Rejected: leaks storage topology and creates an unbounded remote retrieval grant. |
| Invent a LAP upload RPC | Rejected: duplicates A2A's standard `FilePart` byte form and raises interoperability cost. |
| Always permit A2A file parts when the Card lists a file MIME type | Rejected: removes Host and package consent, making an Agent Card an authority grant. |
| Use authenticated object storage for all files | Deferred: correct for large files but needs signed URL, TTL, receiver identity, deletion, and revocation semantics. |

## Open Questions

1. What interoperable receiver acknowledgment, retention class, or deletion
   receipt would be meaningful enough for a future large-file profile?
2. Should a future profile define a portable malware/content-scanning hook, or
   leave scanning as Host-local policy?

Neither question blocks this byte-inline profile because it makes no retention,
deletion, or content-safety claim beyond the Host's existing admission policy.

## Resolution Record

- **Decision:** Pending public review
- **Decision date:** Not applicable
- **Target release:** `0.1.0-draft`
- **Rationale:** Pending implementer and security review.
- **Required follow-up:** Review the profile, vector, and at least one
  independent implementation before acceptance.
