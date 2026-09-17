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
- `../../conformance/core-0.2-wire.json` provides positive cases for all 19
  messages and negative cases for sender, idempotency, Artifact, input,
  terminal-result, and ACK constraints.

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
