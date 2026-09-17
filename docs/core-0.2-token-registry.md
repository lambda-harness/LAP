# Core 0.2 Scoped Token Reference

## Status

Executable reference semantics. This module is not a Core 0.2 Host adapter,
does not make Core 0.2 claimable, and does not provide key management, durable
storage, authenticated session delivery, rate limiting, constant-time lookup,
or an audit sink.

The reference implementation is
[`src/lap_protocol/token_registry.py`](../src/lap_protocol/token_registry.py).
Its executable evidence is
[`tests/test_core_02_token_registry.py`](../tests/test_core_02_token_registry.py).

## Scope

`ScopedTokenRegistry` models a Host-issued capability for exactly two Core
purposes: `artifact_download` and `run_resume`. It makes these portable facts
executable:

- each raw token begins with a protocol marker plus 32 bytes of URL-safe random
  entropy. It never embeds tenant ID, Run ID, audience, purpose, or resource
  identifiers;
- the registry retains only a SHA-256 lookup digest of that raw secret and a
  non-secret `ScopedTokenGrant` record; the raw token is hidden from ordinary
  object representation and returned exactly once at issuance;
- a grant binds one Host-issued tenant/Run scope, audience, purpose, issue time,
  expiry, and opaque grant ID;
- callers receive the grant only when all bindings match and the token remains
  active. Expiry and revocation deny the same raw secret;
- unknown tokens, malformed token text, cross-tenant replays, wrong audience,
  wrong purpose, expired grants, and revoked grants all receive the identical
  `LAP-403: Token is not authorized.` rejection;
- revocation is a Host-management operation that requires the non-secret grant
  ID plus the same Host-issued scope. It never treats possession of a raw token
  as permission to revoke it;
- the registry bounds active grants and removes expired/revoked in-memory
  records before it reserves additional capacity.

## Required Host Transaction

The registry is deliberately local and in-memory. A production Host must make
each issue/revoke decision durable and deliver a raw token through an
authenticated protected channel:

```text
authenticate principal and resolve tenant/Run/session audience
        |
        v
apply purpose, policy, TTL, and capacity decision
        |
        v
persist grant + hashed lookup identity + audit decision
        |
        v
deliver raw secret over protected session/channel exactly once
        |
        v
authorize Artifact/resume endpoint against durable active grant
```

Logout, session rotation, user disablement, tenant offboarding, and Host
failover must revoke or invalidate durable grants before those changes are
considered complete. A Host must rate-limit failed authorization attempts and
evaluate timing side channels; this reference only guarantees the same typed
error payload, not a constant-time distributed service.

## Failure Rules

| Condition | Reference outcome | Host follow-up |
|---|---|---|
| Token from another tenant, audience, or purpose | `LAP-403: Token is not authorized.` | Do not disclose token, Artifact, Run, or tenant existence. |
| Unknown, malformed, expired, or revoked token | same `LAP-403` denial | Rate-limit, audit safely, and keep no resource-specific detail in the response. |
| TTL exceeds policy or capacity is exhausted | typed Host validation/capacity rejection at issuance | Reject before any protected delivery occurs. |
| Grant revocation scope does not match | `false` to Host management caller | Do not reveal the other-scope grant record. |
| Host clock lacks a timezone | typed validation rejection | Fail closed; do not issue a lifetime that cannot be evaluated. |

## Evidence Boundary

The reference tests exercise C02-SEC-01 security semantics. They do not prove
authentication, encryption in transit, session fixation protection, KMS/HSM
integration, durable storage, audit retention, host failover, rate limiting, or
timing-side-channel resistance. Those required Host security tests remain
pending in
[`../conformance/core-0.2-tck.json`](../conformance/core-0.2-tck.json).
