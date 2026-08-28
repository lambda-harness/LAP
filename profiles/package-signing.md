# LAP Package Signing Profile 0.1

**Profile identifier:** `lap-package-signing/0.1`

**Status:** Draft

This optional profile lets a Host verify who signed the exact executable
content of an Agent Package. It adds publisher provenance; it does not grant
installation, tenant access, permissions, workflow dispatch, or automatic
execution by itself.

The profile is designed for package registries and central multi-tenant Hosts.
It is also useful to local Hosts that choose to trust a small publisher set.
An unsigned package remains valid Core 0.1 content unless Host policy requires
a trusted signature.

## 1. Package Content Address

Before signing or verifying, an implementation MUST calculate the lowercase
SHA-256 `package_sha256` over the package tree using this exact byte stream:

1. Begin with ASCII `LAP-PACKAGE-CONTENT-SHA256-v1` followed by one NUL byte.
2. Walk every entry below the package root in lexical order of its UTF-8
   POSIX-relative path bytes.
3. For each directory, append byte `D`, the four-byte unsigned big-endian path
   length, then the UTF-8 path bytes.
4. For each regular file, append byte `F`, the four-byte unsigned big-endian
   path length, the UTF-8 path bytes, the eight-byte unsigned big-endian file
   length, then the exact file bytes.

The single root file `lap-signature.json` is excluded from steps 3 and 4. It is
still subject to package file-count and byte limits. Every other directory and
regular file, including `agent.json`, MUST be included. A package containing a
symbolic link or a non-regular, non-directory entry MUST be rejected.

This exclusion prevents circular signing: the sidecar can attest to a stable
content address without changing it. It does not make the sidecar mutable
trust metadata. A Host MUST bind and recheck the complete sidecar as described
in section 5.

## 2. Signature Sidecar

The signer writes exactly one regular root file named `lap-signature.json`.
It MUST conform to
[`schemas/package-signature.schema.json`](../schemas/package-signature.schema.json)
and contain no additional fields.

```json
{
  "lap": "0.1",
  "algorithm": "ed25519",
  "key_id": "com.example.publisher",
  "agent_id": "com.example.coding-agent",
  "version": "1.2.3",
  "package_sha256": "<64 lowercase hex characters>",
  "signature": "<86 unpadded base64url characters>"
}
```

`agent_id` and `version` MUST exactly match `agent.json`; `package_sha256`
MUST equal the address in section 1. `key_id` identifies a Host-configured
publisher key, not a network endpoint or a public-key value. A malformed,
symlinked, oversized, duplicated, or content-mismatched sidecar MUST be
rejected with `LAP-201` or `LAP-302` before activation.

## 3. Signature Algorithm

`algorithm` is `ed25519`. The signing key signs the following ASCII byte
sequence, including the final newline:

```text
LAP-PACKAGE-SIGNATURE/0.1\n
algorithm=ed25519\n
key_id=<key_id>\n
agent_id=<agent_id>\n
version=<version>\n
package_sha256=<package_sha256>\n
```

The sidecar `signature` is the raw 64-byte Ed25519 signature encoded as
unpadded base64url. A trusted Host public key is the raw 32-byte Ed25519 public
key encoded as unpadded base64url. PEM, JWK, certificates, timestamp tokens,
and key-discovery protocols are intentionally outside this 0.1 profile; a Host
MAY manage them internally before yielding this raw trusted-key mapping.

## 4. Trust and Policy

A Host maps stable `key_id` values to trusted public keys through
administrator-controlled configuration or a tenant-aware policy service. It
MUST NOT obtain the key from the package, a package URL, or an Agent-provided
runtime message.

Verification has three display-safe states:

| State | Meaning |
|---|---|
| `unsigned` | No sidecar is present. |
| `untrusted` | The sidecar is structurally bound to content, but its key is not trusted by this Host. |
| `verified` | The sidecar is bound to content and verifies with the configured public key. |

If a Host enables `require_trusted_package_signatures`, it MUST reject
`unsigned`, `untrusted`, invalid, and mismatched signatures with `LAP-302`.
If that policy is disabled, a Host MAY manually admit `unsigned` or
`untrusted` packages under its normal package policy. A trusted signature MAY
be an additional explicit auto-activation rule, but MUST NOT weaken manifest,
transport, health, tenant-admission, approval, budget, or workflow checks.

The private key MUST NOT be stored in an Agent Package, Host runtime state,
LAP event, audit record, Context Packet, or API response. Hosts SHOULD expose
only `key_id`, profile, algorithm, package digest, and verification state to
users.

## 5. Activation and Snapshots

A Host that evaluates this profile MUST calculate the package content address,
parse and bind the sidecar, then verify its signature against the configured
key map before activation. It MUST repeat that verification after any operation
that can race mutable package storage, including a package copy, archive
extraction, remote admission, or reuse of a prior snapshot.

Because the sidecar is excluded from `package_sha256`, a Host MUST preserve its
full sidecar identity with a release snapshot or otherwise prove that the
reused snapshot has the same complete sidecar. A prefix or content-address
directory MAY be used for storage only if a full sidecar comparison prevents a
collision from selecting the wrong signed release.

Changing executable content, `agent_id`, `version`, or `key_id` creates a new
signature assertion. Re-signing identical executable bytes creates new
provenance even though `package_sha256` remains stable. A Host MUST NOT replace
an active release in place; it validates a candidate and keeps the prior
release available if validation fails.

Removing a key from trust configuration affects future admission. A Host MUST
provide an operator-controlled way to disable or drain already active releases
when revocation requires it; silent mutation of a pinned running release is
not conforming.

## 6. Conformance

An implementation claiming `LAP Package Signing 0.1` MUST satisfy `SIGN-01`
through `SIGN-07` in [CONFORMANCE.md](../CONFORMANCE.md). The reference helper
[`lap_package_signing.py`](../lap_package_signing.py) and
[`tools/package_sign.py`](../tools/package_sign.py) are executable examples,
not a required implementation dependency.
