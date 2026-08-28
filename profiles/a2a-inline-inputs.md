# LAP A2A Inline Inputs Profile

- **Profile:** `lap-a2a-inline-inputs/0.1`
- **Status:** Draft; see [LEP-0001](../proposals/LEP-0001-a2a-inline-inputs.md).
- **Depends on:** [LAP Core 0.1](../SPEC.md),
  [`lap-a2a-bridge/0.1`](a2a-bridge.md), and a negotiated
  [A2A 0.3](https://a2a-protocol.org/v0.3.0/specification/) transport.

## 1. Purpose and Scope

This optional profile permits a Host Runtime to send a small, explicitly
granted Host input artifact to one admitted remote A2A Skill. It uses A2A's
standard `FilePart` with `FileWithBytes.bytes`; it does not define another
file wire protocol.

The profile is intentionally narrow. It covers Host-to-remote input only. It
does not cover remote URL retrieval, Host download of remote output files,
large-file staging, delegated credentials, retention/deletion guarantees, or
remote-to-remote transfer.

## 2. Admission

For every Run carrying one or more input artifacts, all of the following
conditions MUST hold before the Host creates or resumes a remote A2A task:

1. Host policy explicitly enables inline A2A input transfer.
2. The resolved A2A-backed Agent manifest declares
   `transport.input_artifact_transfer: "inline"`.
3. The selected, admitted A2A Skill declares an `inputModes` entry matching
   each artifact media type.

The match is case-insensitive after removing media-type parameters. A Host MAY
support an exact type, `type/*`, or `*/*` wildcard match; it MUST NOT infer
support from a task description, a general Agent Card claim, or a filename.

Failure of condition 1, 2, or 3 MUST produce `LAP-402` before remote dispatch.
The Host MUST NOT drop the artifact and submit only the remaining text.

## 3. Source Verification and Wire Mapping

The Host MUST admit only an already-approved, regular, non-symbolic-link input
file with a stable artifact identifier, basename, media type, size, and
SHA-256 digest. Immediately before serialization it MUST recheck the file
identity and size, read the exact bytes once, and verify the digest. A missing
source is `LAP-404`; malformed artifact metadata is `LAP-201`; a changed
source is `LAP-409`.

For each verified artifact, the Host MUST append this A2A 0.3 part to the
outbound user Message:

```json
{
  "kind": "file",
  "file": {
    "bytes": "<base64 of the verified bytes>",
    "name": "<approved basename>",
    "mimeType": "<approved media type>"
  },
  "metadata": {
    "io.github.dongrv.lap.a2a.inline-inputs": {
      "id": "<Host artifact id>",
      "sha256": "<lowercase SHA-256>",
      "sizeBytes": 123
    }
  }
}
```

`file.uri` MUST be absent. A Host MUST NOT expose a local path, `lap://` URI,
remote URL, tenant identity, user/session token, Host grant, or credential in
this part or its metadata. The metadata namespace is descriptive integrity
evidence; it does not grant access or require the remote Agent to retain it.

The approved artifact digest and identity remain part of the Core idempotency
equivalence relation. A retry for different approved bytes MUST NOT reuse a
task created for the former bytes.

## 4. Bounds and Observability

The Host MUST bound count, raw bytes, Base64 expansion, and the final serialized
network request according to Host policy. It MUST reject an oversized request
with `LAP-401` before remote task creation. A remote response limit is not an
outbound request limit and MUST NOT be used as one.

Progress and audit may record the profile id, artifact count, stable artifact
id, digest, media type, and byte count. They MUST NOT record raw file bytes,
Base64, local paths, unredacted remote URLs, tenant secrets, or credentials.
Progress MUST describe the observable transfer outcome, not hidden reasoning.

## 5. Trust, Privacy, and Retention

Inline transfer discloses the approved bytes to the remote Agent and any
transport/service processors on the selected route. The Host cannot verify
that a remote Agent deletes the bytes, avoids persistence, or restricts
downstream access. Enabling this profile is therefore an administrator trust
decision for a specific remote Agent release and network route, not a promise
of remote retention or deletion.

The bridge's normal Host-owned tenant, authorization, network allow-list,
deadline, cancellation, and terminal-result rules remain in force. This
profile does not delegate a user's broad credentials or let a remote Agent
assert tenant identity.

## 6. Compatibility

The profile is additive and default-deny. Existing `lap-a2a-bridge/0.1`
implementations continue to reject attachment-bearing Runs with `LAP-402`.
Hosts and packages that do not opt in have no wire change. A Host that does not
support this profile MUST reject rather than silently downgrade a requested
attachment transfer.

## 7. Conformance

An implementation claiming this profile MUST satisfy `INLINE-01` through
`INLINE-03` in [CONFORMANCE.md](../CONFORMANCE.md) and pass the portable
[`a2a-inline-inputs.json`](../conformance/a2a-inline-inputs.json) vector. The
vector proves wire shape and admission semantics, not a remote service's
retention/deletion behavior.
