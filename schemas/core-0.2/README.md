# Core 0.2 Schema Foundation

These schemas are draft material for accepted LEP-0010, not a released Core
0.2 conformance claim. Core 0.1 schemas and runtime behavior are unchanged.

- `envelope.schema.json` validates the versioned stream identity, explicit
  sender role, mandatory Run/correlation/idempotency fields, and every
  registered Core payload through a stable `$defs` fragment.
- `message-registry.json` validates registry structure and requires each row to
  point at its payload fragment.
- `registry.json` records sender, criticality, payload fragment, state-machine
  location, and implementation status.
- `state-machine.json` fixes legal activation, Run, and stream event states.
- `tck-registry.schema.json` validates the draft Core 0.2 TCK assertion
  registry and its evidence state.
- `../../conformance/core-0.2-wire.json` provides positive and negative cases
  for all 19 messages, including sender, idempotency, Artifact, input,
  terminal-result, and ACK constraints.
- `../../conformance/core-0.2-tck.json` maps all required Core assertions to
  verified draft evidence or a pending runtime scenario. Its current
  `not_claimable` status is normative for Core 0.2 claims.
- `../../src/lap_protocol/stream_ledger.py` and
  `../../tests/test_core_02_stream_ledger.py` make the epoch, sequence, ACK,
  replay, and checkpoint semantics executable reference evidence. They do not
  replace a Host's durable transaction or upgrade pending runtime assertions.
- `../../src/lap_protocol/artifact_ledger.py` and
  `../../tests/test_core_02_artifact_ledger.py` make Artifact Offer, byte
  validation, receipt, and success-gating semantics executable reference
  evidence. They do not implement a Host object store or upgrade pending
  runtime assertions.
- `../../src/lap_protocol/run_ledger.py` and
  `../../tests/test_core_02_run_ledger.py` make Host-owned Run transitions,
  first-terminal-wins, structured errors, and `indeterminate` semantics
  executable reference evidence. They do not implement Host durability,
  redaction, provider reconciliation, or upgrade pending runtime assertions.
- `../../src/lap_protocol/token_registry.py` and
  `../../tests/test_core_02_token_registry.py` make opaque scoped resume and
  Artifact-token issuance, audience/purpose binding, expiry, revocation, and
  generic cross-scope denial executable reference evidence. They do not
  implement Host key management, durable token storage, or upgrade pending
  runtime assertions.

The payload contracts are fully specified as draft material. A row remains
`draft` until a Host implements it with positive/negative vectors and runtime
conformance evidence. Schema validation alone does not prove transport-peer
identity, epoch fencing, durable ACK, replay, authorization, or terminal-state
correctness.

The `sender` field makes the intended protocol role machine-checkable. It is
not an authorization claim: a transport adapter MUST compare it with the
authenticated/negotiated peer before applying a frame.

ACK messages MUST NOT request acknowledgement themselves. Their criticality
means they convey a durable waterline, not that peers create ACK-of-ACK loops.
