# LAP Rust Echo Agent

This reference implementation exercises the same `lap-local/0.1` round trip as
the Python and Go examples. It uses `serde_json` only for UTF-8 NDJSON framing;
stdout contains protocol envelopes exclusively.

```text
agent.hello -> agent.welcome
run.start   -> run.accepted -> run.progress -> run.result
```

Run the source reference with:

```bash
cargo run --quiet
```

The source manifest deliberately invokes Cargo so the conformance fixture can
run without checking a platform-specific binary into Git. A distributable
package should build the executable, place it below its package root, and
replace `transport.command` with that package-relative entrypoint. The Host
must still explicitly admit the selected launcher before activation.

Use this fixture as a protocol reference, not as a sandbox or authorization
boundary.
