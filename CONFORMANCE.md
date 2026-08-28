# LAP Conformance

An implementation MUST pass the applicable assertions below before claiming a
LAP profile. A conformance report identifies the implementation, version,
operating system, profile version, test suite version, and any optional
extensions.

## Core 0.1

| ID | Assertion |
|---|---|
| CORE-01 | Rejects an unsupported LAP major version during negotiation. |
| CORE-02 | Validates required manifest identity, transport, and capability fields. |
| CORE-03 | Resolves one immutable release before accepting a run. |
| CORE-04 | De-duplicates repeated `run.start` idempotency keys. |
| CORE-05 | De-duplicates replayed `(producer, seq)` events. |
| CORE-06 | Records exactly one immutable terminal result per run. |
| CORE-07 | Preserves a typed failure reason for failed and timed-out runs. |
| CORE-08 | Rejects a child dispatch exceeding policy, depth, budget, or cycle limits. |
| CORE-09 | Keeps tenant-scoped context, artifact, approval, and audit data isolated. |
| CORE-10 | Does not require or persist hidden model reasoning in progress events. |
| CORE-11 | Rejects a declared package integrity target that is absolute, contains traversal, resolves through a symlink, refers to `agent.json`, is not a regular file, or has a mismatched SHA-256 digest. |
| CORE-12 | Treats a lap://run/input/... Context Packet artifact as immutable, digest-identified input; private source paths and ambient storage locators do not enter LAP frames or LAP-visible audit data. |
| CORE-13 | Admits only bounded self-contained Draft 2020-12 capability contracts, validates normalized input before dispatch, includes it in idempotency equivalence, and rejects a purported successful output that violates the declared output contract before caching or workflow binding. |

## Package Signing 0.1

| ID | Assertion |
|---|---|
| SIGN-01 | Calculates the canonical full-package SHA-256 byte stream and excludes only a regular root `lap-signature.json` sidecar. |
| SIGN-02 | Rejects a malformed, symlinked, oversized, identity-mismatched, or content-mismatched sidecar before activation. |
| SIGN-03 | Verifies the exact `lap-package-signing/0.1` Ed25519 message with an explicit Host-controlled `key_id` to raw public-key mapping. |
| SIGN-04 | When trusted signatures are required, rejects unsigned, unknown-key, invalid, and mismatched assertions with `LAP-302`. |
| SIGN-05 | Does not disclose private keys, raw signatures, or unrestricted package paths in a Context Packet, public release record, or LAP-visible audit event. |
| SIGN-06 | Rechecks the complete sidecar and content identity after copying, snapshot reuse, or another mutable-storage boundary; a race cannot substitute a different provenance assertion. |
| SIGN-07 | Does not treat a valid signature as an installation, tenant-admission, permission, approval, or auto-activation grant unless a separate Host policy explicitly permits that action. |

## Local Stdio 0.1

| ID | Assertion |
|---|---|
| LOCAL-01 | Starts the declared command without a shell and inside the package policy boundary. |
| LOCAL-02 | Completes `agent.hello` / `agent.welcome` negotiation with manifest identity match. |
| LOCAL-03 | Rejects malformed JSON, non-protocol stdout, and oversized frames safely. |
| LOCAL-04 | Routes diagnostic output to stderr without corrupting the protocol stream. |
| LOCAL-05 | Emits `run.accepted` before non-terminal events for an accepted run. |
| LOCAL-06 | Maps unexpected process exit to a typed failed terminal result. |
| LOCAL-07 | Enforces cancellation and shutdown grace periods. |
| LOCAL-08 | Validates a hot-reload candidate before activation and retains the old release on failure. |
| LOCAL-09 | Drains existing runs before disable or removal. |
| LOCAL-10 | Stages each granted local input artifact before process start, verifies its SHA-256, bounds item/byte use, and removes the run workspace after completion. |

## A2A Bridge 0.1

| ID | Assertion |
|---|---|
| A2A-01 | Validates Agent Card identity, version, and admitted capabilities at registration. |
| A2A-02 | Persists the negotiated A2A version and card digest with the resolved release. |
| A2A-03 | Maps an A2A terminal task outcome to one LAP terminal result. |
| A2A-04 | De-duplicates stream replay before emitting LAP events. |
| A2A-05 | Does not forward broad caller credentials or trust remote tenant claims. |
| A2A-06 | Rejects an unnegotiated input-artifact transfer before creating a remote task; it never drops the attachment or maps a local URI to a remote URL. |

## A2A Inline Inputs 0.1

| ID | Assertion |
|---|---|
| INLINE-01 | Admits an input artifact only when Host policy enables the profile, the A2A manifest declares `transport.input_artifact_transfer: "inline"`, and the selected admitted A2A Skill declares a matching input MIME mode. |
| INLINE-02 | Rechecks the approved regular source file's identity, size, and SHA-256 immediately before serialization; it sends Base64 bytes in an A2A `FilePart` and never a local path, `lap://` URI, remote URL, tenant identity, or credential. |
| INLINE-03 | Bounds each serialized request before remote task creation, records only safe artifact identity metadata in progress/audit output, and rejects an admission, MIME, mutation, or size failure with a typed error before remote dispatch. |

## Workflow 0.1

| ID | Assertion |
|---|---|
| FLOW-01 | Validates graph node references, unique ids, and terminal edge statuses. |
| FLOW-02 | Rejects cycles and unsupported implicit retry/loop behavior. |
| FLOW-03 | Resolves and pins every Agent Release before the workflow run starts. |
| FLOW-04 | Schedules independent eligible nodes in parallel only within runtime policy. |
| FLOW-05 | Enforces workflow budget, depth, tenant, and approval policy for every dispatch. |
| FLOW-06 | Persists canonical workflow digest, parent/child lineage, and terminal output bindings. |
| FLOW-07 | Rejects an orchestrator proposal that is outside its immutable allow-list, capability set, child-run count, deadline, or dynamic depth bound before starting the proposed child; a dynamic child cannot recursively become an orchestrator. |
| FLOW-08 | Preserves a validated LAP Agent's structured terminal output as the canonical node value; UI text rendering cannot replace it before a downstream binding or declared workflow output resolves. |
| FLOW-09 | When strict output budgeting is requested, requires explicit static and dynamic node allocations, reserves a dynamic allocation before dispatch acceptance, constrains every Host-metered model sub-run, and rejects transports or nested Agent-as-tool executions that cannot share a Host meter. |
| FLOW-10 | If the Host offers YAML workflow author input, bounds and safely parses it, rejects YAML graph/duplicate-key ambiguity and non-JSON data, and normalizes it to the same canonical JSON document before validation, persistence, digesting, or execution. |
| FLOW-11 | Atomically issues a Host-private workflow release admission for the exact external release set and root tenant/session/run; a draining release admits only matching child scope, and new, cross-scope, closed, or fabricated admissions start no target Agent. |

## Host Metering 0.1

| ID | Assertion |
|---|---|
| METER-01 | Treats meter currency, request overhead, and prices as Host-controlled configuration; rejects an absent, malformed, or all-zero price table when a monetary policy is requested. |
| METER-02 | Reserves every observed model request before provider dispatch using a conservative input envelope and a finite applied output cap; a preflight quota failure starts no target Agent or provider request. |
| METER-03 | Shares one atomic root ledger across concurrent nodes and all covered nested model calls; held reservations count against later admissions. |
| METER-04 | Settles only from the provider response bound to that request, falls back to the full reservation when usage is absent, and prices tokens with integer arithmetic. |
| METER-05 | Fails with `LAP-401` and records an auditable reason when reported use exceeds the request envelope, allocation, or root budget; rejects external or independent nested execution that cannot share the ledger. |

## Test Fixtures

The repository includes the portable material in
[`conformance/`](conformance/README.md):

| Kit item | Executable evidence |
|---|---|
| `local-stdio-roundtrip.json` | Valid Core envelopes, ordered producer frames, a digest-identified local input-artifact reference, version/profile selection, correlated acceptance, preserved run identity, and one typed terminal result. |
| `capability-contract.json` | A Draft 2020-12 capability input/output contract with valid and invalid JSON instances for Host-side contract checks. |
| `workflow-budget.json` | A strict workflow output-budget example, an explicit dynamic allocation, and a structurally valid oversubscription that every Host must reject during semantic validation. |
| `workflow-release-admission.json` | A root-scoped external release-admission scenario with matching and rejected child scopes; Hosts use it with implementation-local lifecycle tests. |
| `host-metering.json` | Integer reservation and settlement values for `lap-host-metering/0.1`, including cached input and missing-usage fallback. |
| `a2a-inline-inputs.json` | A three-gate A2A input-file admission vector, exact Base64 `FilePart` mapping, safe metadata, and required pre-dispatch rejections. |
| `conformance-report.schema.json` | A reproducible, machine-readable implementation/profile claim. |
| `tests/test_conformance.py` | Runs the same public local round trip against the Python and Go reference Agents when the Go toolchain is available, and verifies the vector and report schema. |
| `tests/test_package_signing.py` | Verifies the canonical content address, Ed25519 sidecar schema, required-trust rejection, and reference signing CLI. |

Run every published check with:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

The portable kit cannot prove Host-private behavior such as tenant storage
isolation, policy enforcement, process sandboxing, race recovery, or remote
credential handling. An implementation claiming an assertion in those areas
MUST supply implementation-local tests and cite them in a report conforming to
[`schemas/conformance-report.schema.json`](schemas/conformance-report.schema.json).
The public vectors are intentionally stable inputs for those independent tests;
they do not turn a self-issued report into certification.

The [Go Agent SDK](sdk/go/README.md) has its own protocol-loop tests, but those
tests are Agent-side implementation evidence only. They do not constitute a
claim that its caller is a conforming Host Runtime.
