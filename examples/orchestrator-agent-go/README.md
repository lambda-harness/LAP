# LAP Go External Orchestrator Agent

This runnable `lap-local/0.1` package is a Go implementation of a bounded
external workflow orchestrator. It uses the public [Go Agent SDK](../../sdk/go/README.md)
to read the Host-owned
`io.github.dongrv.lap.workflow.orchestrator` Context Packet extension and
return one standard dispatch proposal.

It deliberately contains no target Agent name, capability, credential, Host
path, tenant identifier, or authorization logic. For a repeatable example it
chooses the first Host-provided target and its first permitted capability. A
production planner can use its own reasoning or policy to choose among the
same bounded list.

```text
Host workflow scope -> Context Packet extension -> external Go planner proposal
                                                   -> Host validation -> child run
```

The planner never creates the child itself. The Host still resolves releases,
checks tenant admission, capability scopes, budgets, deadlines, approvals, and
cycles before it can start any target.

## Package Contents

- `agent.json`: a portable package manifest with the `plan.dispatch`
  capability, the published dispatch-output schema shape, and declarations for
  both `lap-local/0.1` and `lap-workflow/0.1`.
- `main.go`: a dependency-free Agent implementation built on the Go SDK.
- `go.mod`: a local SDK replacement so the repository example builds without
  downloading a moving dependency.

The source manifest runs `go run .` so the conformance suite can execute the
same source on supported platforms. A Host must still explicitly allow the Go
executable before activation. The declaration supports workflow preflight, but
the Host still proves the workflow profile in every run's handshake.

## Try It With a Host

1. Copy this directory into the Host's managed LAP package directory, for
   example `lap_agents/orchestrator-agent-go` in a Lambda Harness runtime.
2. Review and explicitly activate the package through the Host's Agent
   management surface. Discovery alone must not execute it.
3. Create an `orchestrated` workflow whose root node uses
   `org.lap.go-orchestrator-agent` with capability `plan.dispatch`.
4. Fill `allowed_agent_ids` and `allowed_capabilities` with Agent IDs and
   capabilities that are already admitted by that Host and tenant.
5. Run the workflow. The Host supplies the exact scope in the Context Packet;
   this example returns one proposal from that scope.

For example, the root node shape is:

```json
{
  "id": "plan",
  "type": "orchestrator",
  "agent": {
    "id": "org.lap.go-orchestrator-agent",
    "capability": "plan.dispatch"
  },
  "allowed_agent_ids": ["com.example.inspector"],
  "allowed_capabilities": {
    "com.example.inspector": ["repo.inspect"]
  }
}
```

Replace the illustrative downstream ID and capability with entries from the
Host's current Agent directory. They are not configured by this package.

## Build a Binary Package

Build a platform-specific executable inside the package, then change the
manifest command to the package-relative binary path:

```powershell
New-Item -ItemType Directory -Force bin
go build -o bin\lap-go-orchestrator.exe .
# agent.json: "command": ["bin/lap-go-orchestrator.exe"]
```

On a POSIX platform, use `go build -o bin/lap-go-orchestrator .` and the
matching slash-separated manifest path. The `bin/` directory is intentionally
not committed. Package review, activation, content validation, and any
publisher signature still happen at the Host boundary.

## Verify the Example

From the repository root:

```bash
go test ./sdk/go/...
python -m unittest discover -s tests -p "test_examples.py" -v
```

The test sends a real `agent.hello` and `run.start` exchange, validates every
returned envelope, and checks both the exact Host-scoped proposal and the
typed `LAP-201` response when the scope is missing. See the [Workflow Profile](../../profiles/workflow.md)
and [LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md) for the normative
contract.
