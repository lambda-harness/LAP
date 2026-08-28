# LAP Workflow Profile

- **Profile:** `lap-workflow/0.1`
- **Depends on:** [LAP Core 0.1](../SPEC.md)

## 1. Purpose

This profile defines a text-first, user-owned workflow graph for composing
managed LAP Agents. A workflow is executable configuration, not a UI drawing:
the UI may render or edit it, but the canonical form is a versioned JSON
document conforming to
[`schemas/workflow.schema.json`](../schemas/workflow.schema.json).

YAML MAY be offered as an authoring convenience only; it is not a second
workflow representation. A Host that accepts YAML MUST treat it as untrusted
text, apply finite source-byte, syntax-event, and nesting limits, and reject
anchors, aliases, duplicate mapping keys, non-string mapping keys, and values
that cannot be losslessly represented as JSON. It MUST normalize the accepted
source to canonical JSON before semantic validation, release persistence,
digest calculation, Agent resolution, or execution. The original YAML text
MUST NOT become a workflow identity, a binding input, or an alternative replay
representation. A runtime persists the canonical document digest and resolved
Agent Releases with every workflow run.

## 2. Execution Model

Nodes become eligible when all inbound dependencies are satisfied. Independent
eligible nodes MAY execute in parallel subject to runtime policy. The optional
`policy.max_parallel_nodes` bound is the workflow's requested cap; the Host
MUST reject a value above its own limit and MUST NOT silently raise it. A node's
Agent Release is resolved before the workflow run begins and remains pinned for
that run. The runtime creates a root run and one child run per executed node;
all child runs carry the root `trace_id` and direct `parent_run_id`.

For every external Agent Release, the Host MUST atomically issue a
**workflow release admission** when it creates the root run. The admission is
Host-private state, not a workflow document field, Context Packet grant, or
Agent-visible envelope value. It MUST bind the exact resolved release set to
the root `tenant_id`, `session_id`, and `workflow_run_id`. A child may use an
otherwise draining release only when its tenant and session match that
admission and its direct `parent_run_id` equals the admitted root run ID. The
Host MUST reject a new root workflow, a different tenant/session/root, a
closed admission, or a fabricated admission before it starts the target Agent.
When the root reaches a terminal state, the Host MUST invalidate the admission.
This permits a disabled release to finish later eligible nodes of an already
admitted graph without letting a new workflow revive that release.

Version `0.1` supports an acyclic graph. Loops, unrestricted expression
evaluation, and implicit retries are out of scope because they make cost and
termination difficult to govern. A future profile may add explicit bounded
loop nodes with separate conformance rules.

## 3. Node Types

| Type | Purpose |
|---|---|
| `agent` | Invoke one admitted Agent capability with declared input. |
| `approval` | Pause until the Host Runtime receives an authorized human decision. |
| `orchestrator` | Ask a designated Agent to propose a permitted child dispatch. |

An `agent` node names its `agent_id`, optional release constraint, and
capability. The runtime validates the capability and resolves the concrete
release. An `approval` node has no direct Agent authority. An `orchestrator`
node may only propose agents listed in its `allowed_agent_ids`; the runtime
must validate every proposal against policy, budget, depth, tenant, and cycle
rules before creating any child run.

### 3.1 Orchestrator Proposal

An orchestrator Agent does not invoke another Agent directly. Its successful
terminal output MUST be exactly one JSON object, with no surrounding prose or
Markdown:

```json
{
  "dispatch": [
    {
      "agent_id": "com.example.inspector",
      "capability": "repo.inspect",
      "input": { "target": "release" }
    }
  ]
}
```

Every proposal MUST contain only `agent_id`, `capability`, JSON `input`, and,
when the parent workflow declares `policy.max_output_tokens`, a `budget` object
with `max_output_tokens`. The latter is an explicit allocation for that one
dynamic child, not a request to raise the workflow's total allowance.
Before starting a proposed child, the Host MUST validate all of the following:

1. The Agent ID is listed by the immutable workflow node and is admitted for
   the current tenant.
2. The resolved release declares the proposed capability.
3. The addition remains within child-run count, deadline, resource-budget, and
   maximum-depth policy. The dynamic child depth is the orchestrator node depth
   plus one and MUST be checked at dispatch time, not only when the static graph
   is validated.
4. The child is a normal Agent invocation. It MUST NOT become an orchestrator
   or recursively acquire a new dispatch authority in the same workflow run.
5. When a strict output budget is active, the Host has atomically reserved the
   proposed child allocation before emitting an accepted dispatch fact. An
   insufficient allocation is a rejection, never an accepted child that is
   later silently throttled.

A rejected proposal MUST produce a typed, observable Host rejection and MUST
NOT start the target Agent. Hosts MAY run independent accepted proposals in
parallel only within `max_parallel_nodes` and all applicable Agent limits;
their recorded outputs retain proposal order.

## 4. Edges and Terminal Policy

Every edge declares the source terminal status that enables it: `succeeded`,
`failed`, `cancelled`, or `timed_out`. A workflow may route failure to a
recovery Agent or stop. If no matching outgoing edge exists, the workflow
completes with that node's terminal status.

The runtime MUST reject a workflow with missing node references, duplicate
node ids, graph cycles, invalid status transitions, unresolved required
capabilities, or declared policy bounds exceeding tenant policy.

## 5. Inputs, Outputs, and Artifacts

Node input is a JSON value. A node MAY reference workflow input or a prior
node's terminal output/artifacts using a JSON Pointer-like `binding` object.
The runtime resolves a binding only when its source node succeeded and MUST
enforce tenant-scoped artifact access. A node may never bind hidden reasoning
or data outside its run lineage.

For a LAP-backed Agent node, the canonical node output is the validated JSON
value from `run.result.payload.output`. A Host MAY render a text projection for
the conversation UI, but MUST NOT replace, stringify, or discard the canonical
JSON before downstream bindings, dynamic dispatch records, artifacts, or
declared workflow outputs are resolved. A result that cannot fit the Host's
structured-output bound MUST fail explicitly rather than being silently
truncated into invalid JSON.

Workflow output is an explicit list of bindings. This makes the deliverable
contract inspectable without reading model prose.

## 6. Budget and Approval

The workflow declares upper bounds for total child runs, execution depth,
parallel eligible nodes, deadline, and optional token/cost budget. The Host Runtime may lower these
bounds but MUST NOT silently raise them. Approval requirements are evaluated
by the Host Runtime for every privileged effect, even when an Agent or
orchestrator requests the dispatch.

### 6.1 Strict Output Allocation

When `policy.max_output_tokens` is present, every static `agent` and
`orchestrator` node MUST declare a positive `budget.max_output_tokens`. The sum of all
static allocations MUST NOT exceed the workflow total. Each accepted dynamic
proposal MUST declare the same field, and the Host MUST reserve it against the
remaining total before it starts the target Agent. A Host MUST reject an
oversubscribed allocation with a typed quota failure; it MUST NOT guess a fair
share, silently rewrite an allocation, or allow a later node to borrow already
reserved output authority.

This rule governs **Host-metered model output**. A Host that directly invokes a
model MUST enforce both a per-request output limit and a bounded number of
model turns such that their product does not exceed the node allocation. It
MUST record the allocation and observed usage in the run audit and fail a
non-conforming adapter whose observed output exceeds the allocation.

Strict output allocation covers every model-consuming sub-run of the node,
including an Agent exposed as a tool. An Agent-as-tool implementation that
starts an independent nested Runner MUST receive the same shared reservation
and Host meter for all of its model calls. If a Host cannot propagate that
authority, it MUST reject the node before the target Agent starts; it MUST NOT
claim that a cap on the outer call bounds the nested execution. A workflow can
instead represent that delegation as explicit nodes and edges.

An Agent transport that runs an independent model is not automatically
Host-metered. A Host MUST reject strict output budgeting for such a transport
unless an interoperable profile lets it independently enforce the same bound.
Agent-reported usage is useful observability, but it is not by itself quota
authority.

`max_input_tokens` and `max_cost_microunits` likewise require a Host-verifiable
metering implementation. A Host that cannot enforce one of those fields MUST
reject that workflow before dispatch rather than accept advisory budget data
and claim enforcement.

The optional [Host Metering Profile](host-metering.md) specifies one direct
Host-model-adapter implementation path. It does not extend the authority of an
external Agent transport: a Host still rejects that transport's strict input,
output, or cost budget until every model-consuming sub-run can use the same
preflight reservation and settlement ledger.

## 7. Lifecycle

```text
draft -> validated -> active -> retired
                \-> failed
```

Publishing a changed workflow creates a new immutable workflow version. A
running instance stays pinned to its canonical graph digest and resolved agent
releases. Disabling an Agent blocks new workflow instances that require it but
does not rewrite existing history. A live root-scoped workflow release
admission remains valid only until that one root reaches a terminal state.

## 8. Minimal Example

```json
{
  "lap": "0.1",
  "id": "com.example.release-check",
  "version": "1.0.0",
  "mode": "declared",
  "policy": { "max_child_runs": 3, "max_depth": 2, "max_parallel_nodes": 2 },
  "nodes": [
    {
      "id": "inspect",
      "type": "agent",
      "agent": { "id": "com.example.inspector", "capability": "repo.inspect" },
      "input": { "binding": "/input" }
    },
    {
      "id": "approve",
      "type": "approval",
      "message": "Approve the generated release report?"
    },
    {
      "id": "publish",
      "type": "agent",
      "agent": { "id": "com.example.publisher", "capability": "report.publish" },
      "input": { "binding": "/nodes/inspect/output" }
    }
  ],
  "edges": [
    { "from": "inspect", "to": "approve", "on": "succeeded" },
    { "from": "approve", "to": "publish", "on": "succeeded" }
  ],
  "outputs": [{ "name": "report", "binding": "/nodes/publish/output" }]
}
```

The same validated document is available as
[`examples/release-check.workflow.json`](../examples/release-check.workflow.json).
