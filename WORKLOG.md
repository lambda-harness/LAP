# Business Agent Expansion Worklog

## 2026-09-16 - Scope and protocol decisions

- Goal: deliver two external LAP Local 0.1 Agents and aggregate release ZIPs
  under `LAP/dist`; the Host remains free of business implementation code.
- Invoice Agent: Python, multiple JPEG/PNG/WebP/GIF/PDF inputs, PDF pages
  rendered locally, DeepSeek `deepseek-flash` vision extraction, validated
  invoice rows, and one downloadable XLSX artifact.
- AIBot Agent: Go, platform-specific binaries. Version 0.1 exposed general
  model chat, bounded log retrieval, and release-command planning; version 0.2
  adds Jenkins execution bound to the signed OA identity.
- Security decision: Jenkins execution never accepts a caller-supplied user
  ID. The company Host projects the authenticated OA AdminID into protected
  run context and the Agent applies the existing project authorization map.
- Credentials stay outside packages. The invoice Agent receives only the
  explicitly delegated `DEEPSEEK_API_KEY`; the AIBot Agent reads a package
  `config.yaml` supplied by the operator and never returns secret fields.

## Acceptance record

Status values: pending, passed, failed, blocked.

| Check | Status | Evidence |
| --- | --- | --- |
| Invoice manifest/package validation | passed | Harness package validator; sanitized ZIP SHA-256 `ea28fa38efc2507b32f6ae5bf36da723f76c240dc8249932185425b03689e1d5` |
| Invoice Local 0.1 exchange | passed | welcome, accepted, progress, artifact, succeeded, shutdown against the sample PDF |
| Multi-image/PDF input staging | passed | digest-checked multi-artifact regression test |
| Sample PDF extraction and XLSX round trip | passed | 20-digit invoice identifier matched the source; 159.25 + 9.55 = 168.80; XLSX reopened successfully |
| AIBot Windows amd64 build | passed | integrity SHA-256 `ff2918b5d8ebbd0ec2d98656955c742c4366e1302c8db1d10997eedd5f820725` |
| AIBot Linux amd64 build | passed | integrity SHA-256 `933c26b0250f5b871ffcdeee88185cca2ffd5d3b820fa9806da7f0bb3ff68263` |
| AIBot manifest/package validation | passed | both platform packages passed Harness validation |
| AIBot Local 0.1 conformance | passed | CORE-02, LOCAL-01/02/05/07; `release.plan` terminal succeeded with no side effect |
| Core 0.2 typed wire draft | passed | 19 positive payload vectors, 8 negative vectors, registry/state-machine coverage, and Core 0.1 isolation test |

## 2026-09-16 - OA-authorized Jenkins execution

- AIBot Agent 0.2 adds `release.execute`; a successful call triggers the
  configured Jenkins API.
- Authorization identity is the OA `CH_AdminID` extracted from the Host-signed
  session. Capability input cannot supply or override this identity.
- Every resolved FC/JT target is checked against `dispatch.projectAuthMap`
  before the first Jenkins request. Missing identity, missing policy, or one
  denied target fails closed with no partial release.
- The tenant ID remains the stable user workspace key and is not reused as a
  business authorization identity.
- Windows and Linux packages passed static validation. The Windows build
  passed LAP Local handshake/run conformance. Injected Jenkins tests verify
  authorized execution and denied zero-call behavior without touching Jenkins.
- Release archives: Windows amd64 SHA-256
  `30026444ab339821ce7bb5d7d00f654e9cc68f66b31b587ced60a9a2c1f59a17`;
  Linux amd64 SHA-256
  `263a9606701eddba1c939fc3b344c72590282748ba42faedfc306853c442665b`.

### AIBot operations Agent 0.3 identity compatibility

- Authorization prefers the signed Host actor extension containing the raw OA
  AdminID. For older company Hosts, the Agent accepts only the Host-generated
  LAP run tenant and normalizes `user-118` to AdminID `118`; capability input
  still cannot provide an identity.
- Authorization rejection now uses the protocol-valid `failed` terminal with
  `LAP-403`, rather than the unsupported `denied` terminal status.
- Windows amd64 ZIP SHA-256:
  `d8b5c875eb751355f3b85e684722efcb91f79787e4ca12adfb83f4c04ee6ef25`.
- Linux amd64 ZIP SHA-256:
  `69e32206125ab94b6d1c2129871288e9c6bed18cc5500c277f85bd53ffce8750`.

## 2026-09-17 - Core 0.2 typed-wire baseline

- Core 0.2 now has a self-contained draft envelope with one addressable payload
  contract for each of the 19 registered Core messages. The registry maps each
  message to a stable JSON Pointer rather than duplicating partially divergent
  schema files.
- The envelope has an explicit `sender` role. It enables schema and TCK checks,
  but it is not an authorization mechanism: a Host transport must still match
  it to its authenticated or negotiated peer.
- A machine-readable activation/Run/stream state matrix records legal prior
  states. It preserves the Core decision that only the Host writes the
  authoritative Run ledger; a Schema or Agent event cannot rewrite terminal
  history.
- The `indeterminate` terminal state is represented in `run.result` and
  `run.result.ack`; it requires a structured error and does not permit a blind
  success fallback.
- The portable wire vector covers one valid instance of every Core message and
  one invalid instance of every Core message, including sender, idempotency,
  Artifact, input, terminal-result, and ACK cases.
- The Core 0.2 TCK registry now tracks all 13 required assertions. Only the
  typed-wire assertion has verified draft evidence; all Host-runtime assertions
  are explicitly pending, and the registry prohibits a Core 0.2 claim until
  its listed blockers are closed.
- This remains draft contract evidence only. Stream fencing, durable ACK,
  replay, authorization, and terminal persistence remain Host runtime work.

## 2026-09-17 - Core 0.2 reference stream ledger

- Added an executable, isolated stream state machine to the installable Python
  reference kit. It enforces sequential epochs, fences stale appenders, rejects
  gaps and same-position conflicts, produces idempotent duplicate results, and
  exposes bounded replay with explicit unavailability.
- Replay body retention is intentionally separate from duplicate identities.
  An evicted body cannot cause a conflicting old frame to be silently treated
  as a valid duplicate.
- The reference checkpoint preserves waterlines, retained bodies, and all
  duplicate identities across a restart. Tests cover lost-ACK replay, stale
  writer fencing, sequence gaps, retention, and checkpoint restoration.
- The reference remains in-memory by design. A commercial Host must persist
  its checkpoint, run-state update, and outbound ACK intent atomically; TCK
  C02-STREAM-01..03 and C02-RESUME-01 remain pending Host fault injection.

## 2026-09-17 - Core 0.2 reference Artifact ledger

- Added an executable, isolated Artifact Offer/receipt state machine to the
  installable Python reference kit. It validates immutable Offer metadata,
  policy and quota boundaries, exact byte size/SHA-256, opaque scoped receipts,
  and the rule that required deliverables must be receipted before success.
- Duplicate Offer/commit behavior is explicit: the same identity is
  idempotent; the same Artifact ID with changed identity fails as `LAP-109`.
  Validation failure creates no receipt or download-capable reference.
- Receipt selection is scope-bound and returns identifiers only. The reference
  never exposes a source path or stores deliverable bytes itself.
- A commercial Host must atomically persist copied bytes, the receipt/audit
  record, outbound `artifact.committed`, and terminal gate. TCK C02-ART-01..03
  remain pending Host integration and fault injection.

## 2026-09-17 - Core 0.2 reference Run ledger and safe errors

- Added an executable, isolated Host-owned Run state machine to the installable
  Python reference kit. It records lifecycle transitions and first-terminal
  wins under an in-process lock; later terminal evidence becomes a deduplicated
  anomaly rather than rewriting the authoritative history.
- `run.result` proposals now have a reference parser for the existing strict
  Core shape. Successful results must pass required Artifact receipt gating;
  all other terminal results validate any referenced receipt without requiring
  every deliverable.
- `SafeError` validates only the protocol shape and returns defensive copies.
  Hosts still own redaction before audit or diagnostics. An `indeterminate`
  terminal is explicitly non-retryable for the original Run and signals the
  later Profile reconciliation boundary.
- The reference has no durable transaction, distributed lease, effect-provider
  adapter, secret redaction service, or outbox. TCK C02-RUN-01/02 and
  C02-ERR-01 remain pending Host/runtime evidence.
