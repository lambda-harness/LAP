# LAP Model Relay Profile (Draft)

- **Profile:** `lap-model-relay/0.1`
- **Status:** Draft; not currently claimable
- **Depends on:** [LAP Core 0.1](../SPEC.md), [Local Stdio](local-stdio.md), and
  [Host Metering](host-metering.md)
- **Proposal:** [LEP-0009](../proposals/LEP-0009-host-model-relay.md)

## 1. Purpose

This profile gives a supervised Local Agent a bounded way to ask its Host to
perform a model request. It is a Host-mediated request path, not an Agent
billing API. The Host retains provider credentials, route selection, policy,
quota reservation, response observation, settlement, cancellation, and audit.

An Agent's own token or cost statement never makes this profile enforceable.
Strict external workflow budgets require both the relay and deployment-enforced
egress isolation that prevents direct model-provider calls outside it.

## 2. Negotiation and Context

The package declares both `lap-local/0.1` and `lap-model-relay/0.1`. For a
Run that requires the relay, the Host offers both profiles in `agent.hello` and
verifies both in `agent.welcome` before `run.start`. Missing support is a
`LAP-204` pre-dispatch rejection.

The Host may include only this exact Context Packet extension:

```json
{
  "io.github.lambda-harness.lap.model-relay": {
    "version": "0.1",
    "routes": [
      {
        "id": "host.default",
        "max_requests": 4,
        "max_output_tokens": 512
      }
    ]
  }
}
```

The extension validates against
[`model-relay-context.schema.json`](../schemas/model-relay-context.schema.json).
Route IDs are opaque and Host-selected. They are not provider names, URLs,
credentials, or authority to use a route not granted for this release and Run.
The Host MUST emit routes in strictly increasing `id` order with no duplicate;
an empty, duplicate, or out-of-order route set is `LAP-201` before `run.start`.

## 3. Relay Exchange

After `run.accepted`, an Agent may send a `model.request` for one granted
route. It carries the exact model-adapter input and a finite
`max_output_tokens`, and is idempotent through the Core Envelope's
`idempotency_key`.

The Host validates the request before contacting a provider, applies its
route policy, reserves the request in the shared workflow ledger, and replies
with one correlated `model.response`. The payload shapes are fixed by
[`model-relay-request.schema.json`](../schemas/model-relay-request.schema.json)
and
[`model-relay-response.schema.json`](../schemas/model-relay-response.schema.json).

The profile intentionally leaves the `input` and `output` objects
route-defined. It standardizes their governance, not a proprietary provider's
prompt or response format. The Host includes a digest of its final provider
request so audit and replay can bind the response to the request it actually
dispatched.

An equivalent replay returns the original response and starts no second
provider call. A non-equivalent reuse of the idempotency key fails with
`LAP-201`; an unauthorized route fails with `LAP-302`; an over-limit request
fails with `LAP-401`. Those failures happen before a provider request.
Failed `model.response` payloads carry only the typed error and request digest;
they MUST NOT contain a partial output or a billable usage settlement.

## 4. Metering and Isolation

For strict input, output, or cost budgets, the Host claims this profile only
when it can prove all model-consuming work in scope reaches the same
Host-owned meter. That requires:

1. a valid `lap-host-metering/0.1` configuration and root workflow ledger;
2. per-request reservation before the Host provider call and settlement from
   the provider response or a conservative reservation fallback;
3. a Local process isolation policy controlled by the deployment, not the
   Agent, that denies outbound network access by default and allows only the
   Host relay endpoints needed for the Run; and
4. rejection of nested or delegated work that can consume models outside the
   ledger.

Without every condition, a Host may expose no relay at all or use it only as
observability. It MUST continue to reject strict external budgets; it must not
accept an Agent's post-hoc usage report as a substitute.

## 5. Security and Audit

The Host MUST bind the request to the existing Local run identity and exact
activated release. It MUST keep provider API keys, endpoints, broad tenant
policy, raw internal prompts, and unrestricted capabilities out of the Context
Packet and public audit stream.

Safe audit facts include the negotiated profile, opaque route ID, request
digest, bounded reservation, settlement source, and typed failure. Raw prompt
or response content, hidden reasoning, credentials, and private paths are not
safe audit facts.

## 6. Current Status

This is a draft contract. LAP Core 0.1 does not yet register the proposed
`model.request` and `model.response` envelope types, and no current Host may
claim `lap-model-relay/0.1`. The portable vector documents the intended
behavior for review without weakening current external-budget rejection.
