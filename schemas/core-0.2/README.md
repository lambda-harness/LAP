# Core 0.2 Schema Foundation

These schemas are draft material for accepted LEP-0010, not a released Core
0.2 conformance claim. Core 0.1 schemas and runtime behavior are unchanged.

- `envelope.schema.json` validates the versioned stream identity and mandatory
  Run, correlation, and idempotency fields.
- `message-registry.json` validates registry structure.
- `registry.json` records sender, criticality, and implementation status.

All payload contracts remain draft. A payload Schema, positive/negative vectors,
sender and state validation, and executable tests are required before any row
can be marked implemented. Schema validation alone does not prove epoch
fencing, durable ACK, replay, authorization, or terminal-state correctness.

ACK messages MUST NOT request acknowledgement themselves. Their criticality
means they convey a durable waterline, not that peers create ACK-of-ACK loops.
