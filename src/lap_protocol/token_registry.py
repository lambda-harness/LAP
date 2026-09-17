"""Reference Core 0.2 scoped-token and cross-tenant denial semantics.

The registry models the portable properties of resume and Artifact access
tokens: opaque high-entropy secrets, Host-issued scope and audience binding,
bounded lifetime, revocation, and one indistinguishable external denial. It is
not a production key-management service, session store, rate limiter, or audit
database. A Host must persist issuance and revocation before exposing a token.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Final, cast

from .artifact_ledger import ArtifactScope

_TOKEN_PURPOSES: Final = frozenset(("artifact_download", "run_resume"))
_DEFAULT_MAX_TTL: Final = timedelta(minutes=15)
_DEFAULT_MAX_ACTIVE_TOKENS: Final = 4096
_TOKEN_DOMAIN: Final = "lap2_"


class TokenRegistryError(ValueError):
    """Represent a safe typed scoped-token registry rejection."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the rejection with a stable LAP code and safe message."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class TokenValidationError(TokenRegistryError):
    """Reject invalid Host-issued scope, policy, audience, or token metadata."""

    def __init__(self, message: str) -> None:
        """Initialize the Core token-metadata validation rejection."""
        super().__init__("LAP-201", message)


class TokenCapacityError(TokenRegistryError):
    """Reject issuance when the Host cannot reserve one more active token."""

    def __init__(self, message: str) -> None:
        """Initialize the Host token-capacity rejection."""
        super().__init__("LAP-401", message)


class TokenDeniedError(TokenRegistryError):
    """Deny all unknown, expired, revoked, or scope-mismatched token requests."""

    def __init__(self) -> None:
        """Initialize the deliberately indistinguishable external denial."""
        super().__init__("LAP-403", "Token is not authorized.")


@dataclass(frozen=True)
class ScopedTokenGrant:
    """Non-secret Host-issued token grant metadata safe for an audit record."""

    grant_id: str
    scope: ArtifactScope
    audience: str
    purpose: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class IssuedScopedToken:
    """One sensitive token return value paired with non-secret grant metadata."""

    token: str = field(repr=False, compare=False)
    grant: ScopedTokenGrant


@dataclass
class _TokenRecord:
    """Keep one in-memory secret digest and grant state without raw token bytes."""

    token_digest: str
    grant: ScopedTokenGrant
    revoked_at: datetime | None = None


class ScopedTokenRegistry:
    """Issue and authorize same-scope Core Artifact/resume token capabilities.

    The Host calls this reference only after authenticating the requesting
    principal and resolving its current tenant/Run scope. ``authorize`` emits
    the same `LAP-403` object for unknown, expired, revoked, audience-mismatched,
    purpose-mismatched, and cross-scope tokens, so its result does not reveal
    which protected resource might exist.
    """

    def __init__(
        self,
        *,
        max_ttl: timedelta = _DEFAULT_MAX_TTL,
        max_active_tokens: int = _DEFAULT_MAX_ACTIVE_TOKENS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create one bounded registry with a Host-controlled UTC clock.

        Args:
            max_ttl: Largest individual token lifetime the Host permits.
            max_active_tokens: Maximum active in-memory grants before issuance
                is rejected.
            clock: Optional UTC-aware clock for deterministic Host tests.

        Raises:
            TokenValidationError: If the registry policy is invalid.
        """
        self._max_ttl = _positive_duration(max_ttl, "max_ttl")
        self._max_active_tokens = _positive_int(max_active_tokens, "max_active_tokens")
        self._clock = _utc_now if clock is None else clock
        self._records_by_digest: dict[str, _TokenRecord] = {}
        self._records_by_grant_id: dict[str, _TokenRecord] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        scope: ArtifactScope,
        *,
        audience: str,
        purpose: str,
        ttl: timedelta,
    ) -> IssuedScopedToken:
        """Issue one opaque, scope-bound, audience-bound, expiring capability.

        The raw token is returned exactly once and is intentionally absent from
        ``ScopedTokenGrant`` and registry records. The caller must send it only
        through its protected Host delivery channel.
        """
        validated_scope = _scope(scope)
        validated_audience = _opaque_id(audience, "audience")
        validated_purpose = _purpose(purpose)
        requested_ttl = _positive_duration(ttl, "ttl")
        if requested_ttl > self._max_ttl:
            raise TokenValidationError("Token lifetime exceeds the Host policy.")
        with self._lock:
            now = self._now()
            self._purge_expired_locked(now)
            if len(self._records_by_digest) >= self._max_active_tokens:
                raise TokenCapacityError("Active token capacity is exhausted.")
            try:
                expires_at = now + requested_ttl
            except OverflowError as exc:
                raise TokenValidationError(
                    "Token lifetime is outside the Host clock range."
                ) from exc
            token, digest = self._new_token_locked()
            grant = ScopedTokenGrant(
                grant_id=self._new_grant_id_locked(),
                scope=validated_scope,
                audience=validated_audience,
                purpose=validated_purpose,
                issued_at=now,
                expires_at=expires_at,
            )
            record = _TokenRecord(token_digest=digest, grant=grant)
            self._records_by_digest[digest] = record
            self._records_by_grant_id[grant.grant_id] = record
            return IssuedScopedToken(token=token, grant=grant)

    def authorize(
        self,
        token: Any,
        *,
        scope: ArtifactScope,
        audience: str,
        purpose: str,
    ) -> ScopedTokenGrant:
        """Authorize one exact request or return the generic safe denial.

        Invalid raw token text uses the same externally observable rejection as
        an unknown token. Scope, audience, and purpose are Host-resolved request
        context and are checked only after their local shape is valid.
        """
        validated_scope = _scope(scope)
        validated_audience = _opaque_id(audience, "audience")
        validated_purpose = _purpose(purpose)
        digest = _untrusted_token_digest(token)
        with self._lock:
            now = self._now()
            record = self._records_by_digest.get(digest)
            if (
                record is None
                or record.revoked_at is not None
                or record.grant.expires_at <= now
                or record.grant.scope != validated_scope
                or record.grant.audience != validated_audience
                or record.grant.purpose != validated_purpose
            ):
                raise TokenDeniedError()
            return record.grant

    def revoke(self, grant_id: str, *, scope: ArtifactScope) -> bool:
        """Revoke one same-scope grant without exposing other-scope metadata.

        This Host-management method returns false for unknown, already revoked,
        expired, or scope-mismatched grants. It never accepts the raw token as
        proof of revocation authority.
        """
        identifier = _opaque_id(grant_id, "grant_id")
        validated_scope = _scope(scope)
        with self._lock:
            now = self._now()
            record = self._records_by_grant_id.get(identifier)
            if (
                record is None
                or record.revoked_at is not None
                or record.grant.expires_at <= now
                or record.grant.scope != validated_scope
            ):
                return False
            record.revoked_at = now
            return True

    def purge_expired(self) -> int:
        """Remove expired or revoked in-memory records and return their count."""
        with self._lock:
            return self._purge_expired_locked(self._now())

    def active_count(self) -> int:
        """Return the current active grant count after local expiry cleanup."""
        with self._lock:
            self._purge_expired_locked(self._now())
            return len(self._records_by_digest)

    def _new_token_locked(self) -> tuple[str, str]:
        """Generate one high-entropy raw token and a unique in-memory digest."""
        while True:
            token = f"{_TOKEN_DOMAIN}{secrets.token_urlsafe(32)}"
            digest = _token_digest(token)
            if digest not in self._records_by_digest:
                return token, digest

    def _new_grant_id_locked(self) -> str:
        """Generate one opaque non-secret grant identifier for Host audit use."""
        while True:
            grant_id = f"grant-{secrets.token_urlsafe(18)}"
            if grant_id not in self._records_by_grant_id:
                return grant_id

    def _purge_expired_locked(self, now: datetime) -> int:
        """Delete records whose token secret is no longer authorized."""
        expired_digests = [
            digest
            for digest, record in self._records_by_digest.items()
            if record.revoked_at is not None or record.grant.expires_at <= now
        ]
        for digest in expired_digests:
            record = self._records_by_digest.pop(digest)
            del self._records_by_grant_id[record.grant.grant_id]
        return len(expired_digests)

    def _now(self) -> datetime:
        """Read and validate one UTC-aware Host clock value."""
        try:
            value = self._clock()
        except Exception as exc:
            raise TokenValidationError("Host token clock is unavailable.") from exc
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise TokenValidationError("Host token clock must be timezone-aware.")
        return value.astimezone(timezone.utc)


def _scope(value: Any) -> ArtifactScope:
    """Require one Host-issued tenant and Run scope object."""
    if not isinstance(value, ArtifactScope):
        raise TokenValidationError("Token scope must be Host-issued.")
    return value


def _opaque_id(value: Any, label: str) -> str:
    """Validate one bounded valid-UTF-8 opaque Host identifier."""
    if not isinstance(value, str) or not value:
        raise TokenValidationError(f"{label} must be a non-empty string.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TokenValidationError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise TokenValidationError(f"{label} must be at most 240 bytes.")
    return value


def _purpose(value: Any) -> str:
    """Require one negotiated Core token purpose rather than ambient access."""
    if not isinstance(value, str) or value not in _TOKEN_PURPOSES:
        raise TokenValidationError("Token purpose is unsupported.")
    return value


def _positive_duration(value: Any, label: str) -> timedelta:
    """Require one positive finite duration without implicit Host defaults."""
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise TokenValidationError(f"{label} must be a positive duration.")
    return value


def _positive_int(value: Any, label: str) -> int:
    """Require one positive non-boolean Host reservation count."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TokenValidationError(f"{label} must be a positive integer.")
    return cast(int, value)


def _untrusted_token_digest(value: Any) -> str:
    """Digest untrusted raw token text without exposing a validation distinction."""
    if not isinstance(value, str):
        return _token_digest("")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return _token_digest("")
    if not value.startswith(_TOKEN_DOMAIN) or len(encoded) > 512:
        return _token_digest("")
    return hashlib.sha256(encoded).hexdigest()


def _token_digest(value: str) -> str:
    """Return the non-secret SHA-256 lookup identity for one raw token."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    """Return the default UTC-aware clock value for production-like use."""
    return datetime.now(timezone.utc)
