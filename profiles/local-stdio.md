# LAP Local Stdio Profile

- **Profile:** `lap-local/0.1`
- **Depends on:** [LAP Core 0.1](../SPEC.md)

## 1. Purpose

This profile runs an external local Agent Implementation as a supervised child
process. It supports a package-provided binary, script, or launcher written in
any language that can read stdin and write stdout.

It is a local IPC profile, not a network service. A Host Runtime owns process
creation, lifecycle, resource limits, working directory, and capability
grants. The agent process never becomes a trusted host controller.

## 2. Package Requirements

The manifest transport MUST be:

```json
{
  "kind": "lap-local",
  "command": ["bin/agent-entrypoint"],
  "working_directory": "."
}
```

`command` is an argument vector, not a shell command. The Host MUST resolve it
inside the validated package root and MUST NOT invoke a command shell. A Host
MAY add fixed, documented runtime arguments but MUST NOT interpolate untrusted
user input into process arguments.

An optional executable or script digest is explicit rather than inferred:

```json
{
  "integrity": {
    "path": "bin/agent-entrypoint",
    "sha256": "<lowercase SHA-256 of that file>",
    "publisher": "Example Publisher"
  }
}
```

`path` is package-relative, names one regular file other than `agent.json`, and
contains no absolute or traversal segment. If `sha256` is present, the Host
MUST verify it before the package is accepted or activated. This detects a
deviation from the manifest declaration; it does not authenticate the package.
The 0.1 `publisher` value is display/provenance metadata; it is not a
signature.

## 3. Stream Rules

- The Host writes one UTF-8 JSON Core Envelope followed by `LF` to the agent's
  stdin.
- The Agent writes one UTF-8 JSON Core Envelope followed by `LF` to stdout.
- stdout is reserved exclusively for valid LAP messages. Diagnostic logs go to
  stderr; a non-JSON stdout line is a framing violation.
- A profile implementation MUST reject a line longer than 1 MiB before parsing.
  Hosts MAY configure a smaller limit.
- The process MUST not depend on terminal control sequences, prompts, or an
  interactive console.
- The Host MUST close stdin and terminate the process on fatal framing or
  protocol-version violation.

## 4. Negotiation

After spawning a candidate process, the Host sends `agent.hello` within five
seconds. The Agent MUST respond with `agent.welcome` within five seconds.
Those defaults MAY be configured by the Host but MUST be recorded in audit
events when exceeded.

`agent.welcome.payload` MUST contain:

```json
{
  "selected_lap": "0.1",
  "profiles": ["lap-local/0.1"],
  "agent_id": "com.example.coding-agent",
  "version": "1.0.0",
  "max_concurrency": 1
}
```

The `profiles` array is the Agent's supported profile set and MUST include
`lap-local/0.1`. A Host MAY include dependent profiles in
`agent.hello.payload.profiles`. When the Host requires one of those profiles
for a Run, it MUST verify that the Agent includes the same identifier in
`agent.welcome.payload.profiles` before it sends `run.start`; a missing required
profile is a `LAP-204` pre-dispatch rejection. An Agent MAY advertise additional
optional profiles so older Hosts can ignore an unknown capability without
losing normal `lap-local/0.1` compatibility.

The Host MUST compare `agent_id`, `version`, and required profiles with the
validated package and requested Run. A mismatch fails the affected activation
or pre-dispatch negotiation. A successful Local negotiation is a health check
for this profile and permits transition to `ready` or `active`.

## 5. Run Exchange

For an accepted `run.start`, the agent MUST first send `run.accepted` with
`correlation_id` set to the start message `id`. The Agent MAY then emit zero or
more `run.progress` and `run.artifact` envelopes. It MUST eventually emit one
`run.result` unless the Host terminates the process.

Example:

```text
Host  -> agent.hello
Agent -> agent.welcome
Host  -> run.start
Agent -> run.accepted
Agent -> run.progress
Agent -> run.artifact
Agent -> run.result
Host  -> agent.shutdown
Agent -> process exit 0
```

An Agent that cannot accept a run MUST emit a terminal `run.result` with
`status: "failed"` and a `LAP-2xx` or `LAP-4xx` error. It MUST NOT silently
drop a `run.start`.

## 6. Input Artifact Grants

If a Context Packet contains an artifact whose URI is
"lap://run/input/<opaque-name>", the Host grants that file only to the current
local Run. The reference MUST carry the exact byte SHA-256 required by LAP
Core. It is not a general file URL and MUST NOT reveal the source path from
which the Host obtained the file.

Before the Host starts the child process, it MUST:

1. create a fresh LAP_RUN_ROOT owned by the Run;
2. stage each granted source as a regular, non-symlink file below
   LAP_RUN_ROOT/input/<opaque-name> without allowing traversal or an existing
   destination;
3. enforce Host byte and item limits and verify the copied bytes against the
   advertised SHA-256; and
4. remove the run workspace after the process has drained or been terminated.

The Agent resolves the URI only as the corresponding path below its supplied
LAP_RUN_ROOT/input directory. It MUST use only Context Packet references and
MUST NOT infer, request, or report an original Host source path. A failed copy,
digest mismatch, source mutation, or unsupported reference is a typed Run
failure before or during execution, never an implicit partial grant.

This mapping narrows what the LAP exchange discloses; it is not an operating
system sandbox. A local process still has the account permissions granted by
the deployment and Hosts SHOULD use an account, container, or VM appropriate
to the package trust level.

## 7. Cancellation and Shutdown

The Host requests cancellation with `run.cancel`. The Agent SHOULD stop
promptly, clean up transient work, and return `run.result` with
`status: "cancelled"`. A Host MAY enforce a grace period and then terminate the
process. If no valid terminal result is observed, the Host records `LAP-500`
and completes the run as failed.

`agent.shutdown` requests graceful process exit after all runs drain. The
default shutdown grace period is ten seconds. A Host MAY terminate a process
after the grace period and MUST record the reason.

## 8. Environment and Isolation

A Host MAY expose these non-secret environment variables:

| Variable | Meaning |
|---|---|
| `LAP_PROTOCOL` | Selected Core protocol version. |
| `LAP_AGENT_ID` | Resolved Agent identifier. |
| `LAP_AGENT_VERSION` | Resolved immutable release version. |
| `LAP_PACKAGE_ROOT` | Read-only absolute package root. |
| `LAP_RUN_ROOT` | Per-run temporary workspace, if granted. |

Tenant identifiers, credentials, and authorization grants MUST travel in the
validated Context Packet or an authenticated side channel, not in ambient
environment variables. The Host SHOULD use a dedicated working directory,
least-privilege filesystem access, resource limits, and a process group/job
object so cancellation includes child processes.

## 9. Hot Reload

When a package changes, the Host MUST treat it as a candidate release. It MUST
validate the new manifest and negotiate a newly spawned process before
activation. Existing runs stay pinned to their resolved process/release. If
validation fails, the old active release remains active and the new candidate
enters `failed` with a recorded reason.
