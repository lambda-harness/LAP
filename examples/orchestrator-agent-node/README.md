# LAP Node.js External Orchestrator Agent

This runnable `lap-local/0.1` package is a dependency-free Node.js reference
implementation of a bounded external workflow orchestrator. It reads the
Host-owned `io.github.lambda-harness.lap.workflow.orchestrator` Context Packet
extension and returns one standard dispatch proposal.

It deliberately contains no target Agent name, capability, credential, Host
path, tenant identifier, or authorization logic. For a repeatable example it
chooses the first Host-provided target and its first permitted capability. A
production planner may choose differently, but the Host still validates every
proposal before it can start a child run.

```text
Host workflow scope -> Context Packet extension -> external planner proposal
                                                   -> Host validation -> child run
```

## Package Contents

- `agent.json`: a portable package manifest with the `plan.dispatch`
  capability, the published dispatch-output schema shape, and declarations for
  both `lap-local/0.1` and `lap-workflow/0.2`.
- `orchestrator_agent.js`: a dependency-free stdin/stdout protocol loop.

The manifest runs `node orchestrator_agent.js` and requires Node.js 18 or
later. A Host must explicitly allow the reviewed `node` executable before
activation. The profile declaration supports discovery and workflow preflight;
it never grants authority or replaces the required handshake before each run.

## Try It With a Host

1. Copy this directory into the Host's managed LAP package directory, for
   example `lap_agents/orchestrator-agent-node` in a Lambda Harness runtime.
2. Review and explicitly activate the package through the Host's Agent
   management surface. Discovery alone must not execute it.
3. Create an `orchestrated` workflow whose root node uses
   `org.lap.orchestrator-agent-node` with capability `plan.dispatch`.
4. Fill `allowed_agent_ids` and `allowed_capabilities` with Agent IDs and
   capabilities that are already admitted by that Host and tenant.
5. Run the workflow. The Host supplies the exact scope in the Context Packet;
   this example returns one proposal from that scope.

## Verify the Example

From the repository root:

```bash
node --check examples/echo-agent-node/echo_agent.js
node --check examples/orchestrator-agent-node/orchestrator_agent.js
python -m unittest discover -s tests -p "test_examples.py" -v
```

The test sends real `agent.hello` and `run.start` exchanges, validates every
returned envelope, and checks that the proposal exactly reflects the
Host-provided Context Packet. See the [Workflow Profile](../../profiles/workflow.md)
and [LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md) for
the normative contract.
