# LAP Echo Agent

This small reference implementation demonstrates the `lap-local/0.1` message
flow. It is intentionally not a production sandbox or authorization system.

Run it with a Host that sends newline-delimited LAP envelopes to stdin. The
agent writes only protocol frames to stdout and sends no diagnostic output.

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

The manifest invokes `python echo_agent.py`. On Windows it may be packaged as
an `.exe`; the protocol behavior does not change.

Use the fixture as a protocol reference, not as a security boundary.
