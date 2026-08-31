# LAP Model Relay Agent (Draft)

This runnable Python Agent demonstrates the proposed `lap-model-relay/0.1`
exchange. It does not contain a provider URL, API key, or direct model client.
It asks its Host for one bounded model response over LAP stdio.

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> model.request
model.response -> run.progress -> run.result
```

Run the deterministic draft probe from the repository root:

```bash
python tools/lap_model_relay_probe.py --package examples/model-relay-agent
```

For an arbitrary declared capability, provide valid JSON explicitly with
`--capability` and `--input`.

The probe simulates a Host response and validates protocol identity, profile
negotiation, Context Packet routes, request idempotency, correlated response,
and the declared capability output. It does not call a model provider, prove
deployment egress isolation, install the package, or certify a Host Runtime.
See [LEP-0009](../../proposals/LEP-0009-host-model-relay.md) for the strict
budget and isolation requirements.
