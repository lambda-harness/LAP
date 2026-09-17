"""Executable Core 0.2 scoped token and cross-tenant denial tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from lap_protocol.artifact_ledger import ArtifactScope
from lap_protocol.token_registry import (
    ScopedTokenRegistry,
    TokenCapacityError,
    TokenDeniedError,
    TokenValidationError,
)

TENANT_A = ArtifactScope("tenant-a", "run-a")
TENANT_B = ArtifactScope("tenant-b", "run-a")


class MutableClock:
    """Expose a deterministic UTC-aware Host clock for token lifecycle tests."""

    def __init__(self) -> None:
        """Initialize the clock at one fixed protocol test instant."""
        self.value = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        """Return the current deterministic clock value."""
        return self.value

    def advance(self, duration: timedelta) -> None:
        """Advance the deterministic protocol clock by one duration."""
        self.value += duration


class Core02TokenRegistryTests(unittest.TestCase):
    """Verify opaque scope, audience, purpose, expiry, and revocation rules."""

    def setUp(self) -> None:
        """Create a fresh bounded registry for each test."""
        self.clock = MutableClock()
        self.registry = ScopedTokenRegistry(
            max_ttl=timedelta(minutes=5),
            max_active_tokens=2,
            clock=self.clock,
        )

    def test_cross_tenant_artifact_and_resume_replay_are_indistinguishable(
        self,
    ) -> None:
        artifact = self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="artifact_download",
            ttl=timedelta(minutes=1),
        )
        resume = self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="run_resume",
            ttl=timedelta(minutes=1),
        )

        artifact_grant = self.registry.authorize(
            artifact.token,
            scope=TENANT_A,
            audience="session-a",
            purpose="artifact_download",
        )
        self.assertEqual(artifact_grant, artifact.grant)
        self.assertNotIn(artifact.token, repr(artifact))

        denials: list[TokenDeniedError] = []
        for token, scope, audience, purpose in (
            (artifact.token, TENANT_B, "session-a", "artifact_download"),
            (artifact.token, TENANT_A, "session-b", "artifact_download"),
            (artifact.token, TENANT_A, "session-a", "run_resume"),
            (resume.token, TENANT_B, "session-a", "run_resume"),
            ("lap2_unknown", TENANT_A, "session-a", "artifact_download"),
            (cast(Any, 1), TENANT_A, "session-a", "artifact_download"),
        ):
            with self.subTest(scope=scope, audience=audience, purpose=purpose):
                with self.assertRaises(TokenDeniedError) as raised:
                    self.registry.authorize(
                        token, scope=scope, audience=audience, purpose=purpose
                    )
                denials.append(raised.exception)
        self.assertEqual(
            {str(error) for error in denials}, {"LAP-403: Token is not authorized."}
        )

    def test_expiry_and_revocation_fail_closed_without_revealing_grant_state(
        self,
    ) -> None:
        issued = self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="artifact_download",
            ttl=timedelta(seconds=30),
        )
        self.assertTrue(self.registry.revoke(issued.grant.grant_id, scope=TENANT_A))
        self.assertFalse(self.registry.revoke(issued.grant.grant_id, scope=TENANT_A))
        self.assertFalse(self.registry.revoke(issued.grant.grant_id, scope=TENANT_B))
        with self.assertRaises(TokenDeniedError) as revoked:
            self.registry.authorize(
                issued.token,
                scope=TENANT_A,
                audience="session-a",
                purpose="artifact_download",
            )

        expiring = self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="run_resume",
            ttl=timedelta(seconds=30),
        )
        self.clock.advance(timedelta(seconds=30))
        with self.assertRaises(TokenDeniedError) as expired:
            self.registry.authorize(
                expiring.token,
                scope=TENANT_A,
                audience="session-a",
                purpose="run_resume",
            )
        self.assertEqual(str(revoked.exception), str(expired.exception))
        self.assertEqual(self.registry.purge_expired(), 1)
        self.assertEqual(self.registry.active_count(), 0)

    def test_policy_capacity_and_clock_validation_reject_unsafe_host_configuration(
        self,
    ) -> None:
        with self.assertRaises(TokenValidationError):
            ScopedTokenRegistry(max_ttl=timedelta(0))
        with self.assertRaises(TokenValidationError):
            ScopedTokenRegistry(max_active_tokens=True)
        with self.assertRaises(TokenValidationError):
            self.registry.issue(
                TENANT_A,
                audience="session-a",
                purpose="artifact_download",
                ttl=timedelta(minutes=6),
            )
        with self.assertRaises(TokenValidationError):
            self.registry.issue(
                cast(ArtifactScope, "untrusted-scope"),
                audience="session-a",
                purpose="artifact_download",
                ttl=timedelta(seconds=1),
            )
        with self.assertRaises(TokenValidationError):
            self.registry.issue(
                TENANT_A,
                audience="",
                purpose="unsupported",
                ttl=timedelta(seconds=1),
            )

        self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="artifact_download",
            ttl=timedelta(seconds=1),
        )
        self.registry.issue(
            TENANT_A,
            audience="session-b",
            purpose="run_resume",
            ttl=timedelta(seconds=1),
        )
        with self.assertRaises(TokenCapacityError):
            self.registry.issue(
                TENANT_A,
                audience="session-c",
                purpose="artifact_download",
                ttl=timedelta(seconds=1),
            )

        naive_clock = ScopedTokenRegistry(clock=lambda: datetime(2026, 9, 17))
        with self.assertRaises(TokenValidationError):
            naive_clock.issue(
                TENANT_A,
                audience="session-a",
                purpose="artifact_download",
                ttl=timedelta(seconds=1),
            )

        near_clock_limit = ScopedTokenRegistry(
            max_ttl=timedelta(days=1),
            clock=lambda: datetime.max.replace(tzinfo=timezone.utc),
        )
        with self.assertRaises(TokenValidationError):
            near_clock_limit.issue(
                TENANT_A,
                audience="session-a",
                purpose="artifact_download",
                ttl=timedelta(days=1),
            )

    def test_issued_grant_is_scope_bound_and_raw_token_is_not_audit_metadata(
        self,
    ) -> None:
        issued = self.registry.issue(
            TENANT_A,
            audience="session-a",
            purpose="run_resume",
            ttl=timedelta(seconds=20),
        )
        self.assertTrue(issued.token.startswith("lap2_"))
        self.assertNotIn("tenant-a", issued.token)
        self.assertNotIn("run-a", issued.token)
        self.assertEqual(issued.grant.scope, TENANT_A)
        self.assertEqual(issued.grant.purpose, "run_resume")
        self.assertLess(issued.grant.issued_at, issued.grant.expires_at)


if __name__ == "__main__":
    unittest.main()
