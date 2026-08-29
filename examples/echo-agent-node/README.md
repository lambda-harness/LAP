# LAP Node.js Echo Agent

This dependency-free Node.js reference implementation demonstrates the
`lap-local/0.1` message flow. It is intentionally not a production sandbox or
authorization system.

Run it with a Host that sends newline-delimited LAP envelopes to stdin. The
Agent writes only protocol frames to stdout and sends diagnostics only to
stderr.

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

The manifest invokes `node echo_agent.js` and requires Node.js 18 or later.
A Host must explicitly allow the reviewed `node` executable before activation.
The protocol behavior does not change if the Agent is packaged with a reviewed
runtime or compiled executable.

Use this fixture as a protocol reference, not as a security boundary.
