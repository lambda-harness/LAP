# LAP Effect Execution Profile 0.1

Status: draft, reference implementation available in
`lap_protocol.effect_ledger`.

This profile defines the Host-owned contract for an Agent that causes an
external side effect, such as a Jenkins release, a database mutation, or an
invoice upload. It is deliberately provider-neutral. `effect_type` values are
opaque capability-owned identifiers; the profile does not define credentials,
provider URLs, or provider-specific request bodies.

## Boundary

The Agent may propose an intent containing an opaque `intent_id`, an effect
type, a SHA-256 request digest, and a safe human-readable summary. The Host
must derive the effect rules from the admitted capability release. An Agent
cannot make an effect required, disable approval, increase its quota, or mark
provider acceptance as business success.

The Host owns authorization, approval, provider execution, evidence storage,
reconciliation, audit records, and the atomic decision that closes a Run. Raw
credentials, request bodies, provider URLs, and receipts remain outside LAP
payloads and are represented only by opaque references and digests.

## Context extension

The Host supplies `io.github.lambda-harness.lap.effect` in the scoped Run
context:

```json
{
  "version": "0.1",
  "capability_id": "release.execute",
  "rules": [
    {
      "effect_type": "jenkins.release",
      "required_for_success": true,
      "approval_required": false,
      "max_intents": 1
    }
  ]
}
```

Rules are immutable for the Run. Effect type identifiers must match the
profile grammar, and a Run cannot create more intents of a type than its
`max_intents` value.

## Lifecycle

The Host records these states in order:

`proposed` -> `approval_required` (when configured) -> `authorized` ->
`accepted` -> one terminal state: `settled`, `failed`, or `indeterminate`.

An accepted provider operation is not proof of a business result. A transport
gap enters `unknown`, then `reconciling`; reconciliation must end in one of
the terminal states. `indeterminate` is terminal for this effect record but
requires operator reconciliation and never permits an automatic retry. A new
side effect requires a new Host decision and a new intent.

Effect events are idempotent by event ID and immutable fingerprints. A changed
replay or an event after a terminal state is rejected. The Host must commit a
required effect's terminal evidence together with the successful Run terminal
record; otherwise the Run is rejected with `LAP-104`.

## Safety requirements

- Agent summaries and failure summaries are bounded UTF-8 text and must not
  contain credentials or raw provider payloads.
- `authorization_ref`, `approval_ref`, operation references, and evidence
  references are opaque identifiers, not bearer tokens.
- A Host must verify provider evidence independently of Agent claims.
- Provider failures and unknown outcomes must be visible as safe typed errors;
  the Host must not silently report success.
- This profile does not provide an OS sandbox or a provider client. Those are
  Host deployment responsibilities.

The JSON payload fragments and executable vector are in
`schemas/effect-execution-0.1.schema.json` and
`conformance/effect-execution.json`.
