# LAP Host Metering Profile

- **Profile:** `lap-host-metering/0.1`
- **Depends on:** [LAP Core 0.1](../SPEC.md) and the [Workflow Profile](workflow.md)
- **Scope:** direct, Host-observed model adapters only

## 1. Purpose

This profile lets a Host enforce a workflow's `max_input_tokens` and
`max_cost_microunits` before it sends a model request. It is a Host integration
profile, not an Agent transport and not a billing assertion an Agent may make
about itself. The Host owns its pricing table, request calibration, ledger, and
terminal decision.

An implementation MUST NOT claim this profile merely because an Agent returns
token or cost fields. Agent-reported usage is observability only. A Host claims
this profile only where it sees both the exact pre-provider request and the
provider response usage for every model-consuming sub-run in scope.

## 2. Applicability

The profile applies only when all of the following are true:

1. The Host receives the actual model request after prompt selection,
   instructions, and context filtering, but before network dispatch.
2. The Host sets a real per-request output ceiling and bounds the number of
   model turns so an output reservation is finite.
3. Every response reports provider usage to the same Host ledger, or the Host
   conservatively settles the request at its full reservation.
4. The Host atomically shares that ledger across all parallel nodes and every
   nested model run covered by the workflow node.

If any condition is false, the Host MUST reject the relevant strict budget
before starting the target Agent. In particular, an independent LAP Local,
A2A, or Agent-as-tool Runner is out of scope until it can use the same ledger;
it cannot satisfy this profile with a post-hoc self-report.

## 3. Host-Controlled Meter

The meter is Host configuration, never user workflow input or Agent manifest
data. It contains:

| Field | Requirement |
|---|---|
| `currency` | Uppercase three-letter ISO 4217 currency code. |
| `request_overhead_tokens` (`H`) | Positive integer covering model/provider control tokens not visible in the Host request envelope, including tool and handoff declarations. |
| `input_microunits_per_million` (`Rin`) | Non-negative integer price for uncached input per one million tokens. |
| `cached_input_microunits_per_million` (`Rcache`) | Non-negative integer price for cached input per one million tokens. |
| `output_microunits_per_million` (`Rout`) | Non-negative integer price for output per one million tokens. |

One micro-unit is `10^-6` of the configured currency's major unit. Integer
arithmetic is required; Hosts MUST NOT use floating point for a quota decision.
When `max_cost_microunits` is used, at least one of `Rin`, `Rcache`, or `Rout`
MUST be positive. A Host using a genuinely free model should omit the monetary
policy rather than advertise a cost cap that can never constrain a request.

`H` is a deployment calibration. The Host MUST update it when its provider,
model adapter, maximum tool surface, or rendered control prompt changes. A
Host that cannot establish a conservative value MUST leave the profile disabled
and reject input/cost budgets.

## 4. Request Lifecycle

### 4.1 Preflight Reservation

For each actual model request, the Host forms a deterministic envelope from
the post-filter `system_instructions` and `input_items`. The 0.1 reference
bound is the UTF-8 byte length of a compact JSON envelope plus `H`. A Host MAY
use a tighter tokenizer-aware bound, but it MUST be at least as conservative
as the provider request it sends. Let this input bound be `Uin`; let `Uout` be
the real hard output cap applied to this request.

Before provider dispatch, the Host MUST atomically reserve the request against
the root workflow ledger:

```text
used_input + held_input + Uin <= max_input_tokens

R = ceil(Uin * max(Rin, Rcache) / 1_000_000)
  + ceil(Uout * Rout / 1_000_000)

used_cost + held_cost + R <= max_cost_microunits
```

The input and cost tests are applied only when their respective workflow
policy fields are present. For a cost policy, `Uout` MUST be finite. A failed
test MUST produce a typed `LAP-401` rejection and MUST NOT contact the
provider.

### 4.2 Settlement

After the provider response, the Host settles the same reservation. Let `I`,
`C`, and `O` be provider-reported input, cached-input, and output tokens. If
input or output usage is absent or zero, the Host MUST use `Uin` or `Uout`
respectively. Cached input is used only with a positive provider input report
and is clamped to that report.

The settled cost is:

```text
P = ceil((I - C) * Rin / 1_000_000)
  + ceil(C * Rcache / 1_000_000)
  + ceil(O * Rout / 1_000_000)
```

The Host releases the hold and commits `I` and `P`. If reported usage exceeds
the request bound, the node allocation, or a root budget, the Host MUST mark
the run failed with `LAP-401`, record the reason, and stop admitting further
work. The provider call has already happened in this case; the failure is a
detected adapter/calibration violation, not an excuse to continue execution.

## 5. Audit Evidence

The Host MUST retain enough immutable audit evidence to reconstruct a quota
decision without exposing private reasoning or raw secrets. A reference event
sequence is:

| Event | Required facts |
|---|---|
| `workflow_budget_metered` | `configured` profile facts before node admission, or `reserved` node identity, request hold, and root held/used totals. |
| `workflow_budget_usage` | normalized provider usage, settled totals, and remaining holds. |
| `workflow_budget_rejected` | node identity and the typed reason; no target Agent start follows a preflight rejection. |

These event names are Host observability conventions, not LAP wire messages.
The externally visible LAP run still carries one typed terminal result.

## 6. Security and Non-Goals

The profile does not standardize provider invoices, credential exchange, or an
external Agent billing API. It does not make a model provider's usage endpoint
trusted by itself; the Host is responsible for transport authentication and
for binding the observed response to the request it dispatched. It also does
not authorize tools, Agent installation, tenant access, or delegated spend.

An interoperable profile for external Agent transports requires a separately
verifiable request/usage path and is intentionally outside
`lap-host-metering/0.1`. The [Model Relay Profile draft](model-relay.md)
defines one Local-only path in which the Host observes the actual provider
request and response. It is not current conformance: until the relay and
deployment-enforced egress isolation are implemented, a Host MUST continue to
reject strict external budgets.

The [portable arithmetic vector](../conformance/host-metering.json) fixes the
0.1 rounding and fallback examples. It cannot prove a Host's provider
integration, calibration, or atomic storage; those remain implementation-local
conformance evidence.
