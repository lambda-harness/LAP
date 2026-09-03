# LAP External Orchestrator Agent

This runnable `lap-local/0.1` package demonstrates the smallest useful
external workflow orchestrator. It reads the Host-owned
`io.github.lambda-harness.lap.workflow.orchestrator` Context Packet extension and
returns one standard dispatch proposal.

It deliberately contains no target Agent name, capability, credential, Host
path, tenant identifier, or authorization logic. For a repeatable example it
chooses the first Host-provided target and its first permitted capability. A
production planner would use its own reasoning or policy to choose among the
same bounded list.

```text
Host workflow scope -> Context Packet extension -> external planner proposal
                                                   -> Host validation -> child run
```

The planner never creates the child itself. The Host still resolves releases,
checks tenant admission, capability scopes, budgets, deadlines, approvals, and
cycles before it can start any target.

## Package Contents

- `agent.json`: a portable package manifest with the `plan.dispatch`
  capability, the published dispatch-output schema shape, and declarations for
  both `lap-local/0.1` and `lap-workflow/0.2`.
- `orchestrator_agent.py`: a dependency-free stdin/stdout protocol loop.

The manifest runs `python orchestrator_agent.py`. Packaging it as a Windows
executable or using another language does not change the wire contract.
The declaration lets a Host reject an incompatible workflow early; it does not
replace the required workflow-profile handshake before every run.

## Try It With a Host

1. Copy this directory into the Host's managed LAP package directory, for
   example `lap_agents/orchestrator-agent` in a Lambda Harness runtime.
2. Review and explicitly activate the package through the Host's Agent
   management surface. Discovery alone must not execute it.
3. Create an `orchestrated` workflow whose root node uses
   `org.lap.orchestrator-agent` with capability `plan.dispatch`.
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
    "id": "org.lap.orchestrator-agent",
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

## Verify the Example

From the repository root:

```bash
python -m pytest tests/test_examples.py -v
```

The test sends a real `agent.hello` and `run.start` exchange, validates every
returned envelope, and checks that the proposal exactly reflects the
Host-provided Context Packet. See the [Workflow Profile](../../profiles/workflow.md)
and [LEP-0004](../../proposals/LEP-0004-portable-orchestrator-context.md) for
the normative contract.
