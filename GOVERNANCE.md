# LAP Governance

## Status

LAP is an open draft stewarded initially by its maintainers. The goal is a
vendor-neutral, implementation-friendly specification. The
specification, schemas, examples, and conformance material are released under
Apache-2.0.

## Change Process

Material changes use a **LAP Enhancement Proposal (LEP)**. Start a public
discussion with the [LEP issue form](.github/ISSUE_TEMPLATE/lep.yml), then
submit the completed proposal from
[`proposals/LEP-template.md`](proposals/LEP-template.md) in a pull request.
Exploratory issues are welcome, but they are not approval for a normative
change.

An LEP MUST state the problem, proposed normative change, compatibility impact,
security impact, migration plan, and conformance changes. Maintainers assign a
monotonically increasing four-digit identifier when a proposal enters formal
review. The proposal file is retained in [`proposals/`](proposals/README.md)
and has one of these statuses:

| Status | Meaning |
|---|---|
| Draft | Author-owned proposal; semantics may change. |
| Review | Under public maintainer and implementer review. |
| Accepted | Approved for a stated version target; implementation is pending or in progress. |
| Implemented | Normative text and required conformance material are merged. |
| Rejected | Declined with a recorded rationale. |
| Withdrawn | Removed by its author before acceptance. |
| Superseded | Replaced by a later numbered LEP. |

An accepted change is merged with its version target and test impact. Before a
release containing the change, its normative text, schema/profile changes, and
required conformance assertions MUST be present or the release MUST exclude the
change. No implementation, including a reference implementation, may silently
redefine a published normative field.

Editorial corrections that do not change valid wire behavior, security
boundaries, or conformance outcomes do not require an LEP. Maintainers record
the reason in the pull request.

## Versioning

- Patch releases clarify errata without changing valid behavior.
- Minor releases add backward-compatible optional fields, events, or profiles.
- Major releases may change or remove required semantics.
- Extensions use reverse-DNS identifiers and cannot override Core tenant,
  lifecycle, idempotency, or authorization behavior.

## Compatibility Promise

`0.x` releases are draft and may change after review. A `1.0` release requires
at least two independent conforming implementations, executable conformance
tests, a documented security review, and stable governance for change control.

Until then, maintainers record compatibility decisions in this repository.
