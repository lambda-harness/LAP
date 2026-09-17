"""Executable Core 0.2 release-contract admission tests."""

from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import Any, cast

from lap_protocol.contract_gate import (
    ContractGate,
    ContractMismatchError,
    ContractValidationError,
    ReleaseIdentity,
)

PACKAGE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
CAPABILITY_DIGEST = "sha256:" + "3" * 64
OTHER_DIGEST = "sha256:" + "4" * 64


def release_payload() -> dict[str, Any]:
    """Create one valid Core 0.2 release identity payload."""
    return {
        "agent_id": "io.example.invoice-agent",
        "version": "2.0.0",
        "package_digest": PACKAGE_DIGEST,
        "manifest_digest": MANIFEST_DIGEST,
        "capability_contracts": {
            "invoice.extract": CAPABILITY_DIGEST,
            "invoice.validate": OTHER_DIGEST,
        },
    }


class Core02ContractGateTests(unittest.TestCase):
    """Verify exact release matching before any business context is supplied."""

    def setUp(self) -> None:
        """Create one Host-admitted reference release for each test."""
        self.expected = ReleaseIdentity.from_payload(release_payload())
        self.gate = ContractGate(self.expected)

    def test_digest_mismatch_rejects_before_context_supplier_is_invoked(self) -> None:
        """Keep input, credentials, and other business context behind the gate."""
        mismatch_cases = (
            ("package_digest", OTHER_DIGEST, "package_digest"),
            ("manifest_digest", OTHER_DIGEST, "manifest_digest"),
            (
                "capability_contracts",
                {"invoice.extract": OTHER_DIGEST, "invoice.validate": OTHER_DIGEST},
                "capability_contracts",
            ),
        )
        for field, value, expected_field in mismatch_cases:
            with self.subTest(field=field):
                running = release_payload()
                running[field] = value
                supplied: list[str] = []

                def supply_context() -> dict[str, str]:
                    supplied.append("called")
                    return {"credential": "private-value"}

                with self.assertRaises(ContractMismatchError) as raised:
                    self.gate.admit(running, supply_context)

                self.assertEqual(supplied, [])
                self.assertEqual(raised.exception.code, "LAP-103")
                self.assertEqual(raised.exception.fields, (expected_field,))
                self.assertNotIn("private-value", str(raised.exception))

    def test_exact_identity_admits_context_once_and_returns_defensive_payload(
        self,
    ) -> None:
        """Allow an exact identity and retain no supplied business context."""
        supplied: list[str] = []

        def supply_context() -> dict[str, str]:
            supplied.append("called")
            return {"input_ref": "lap://run/input/invoice"}

        admission, context = self.gate.admit(release_payload(), supply_context)
        self.assertEqual(supplied, ["called"])
        self.assertEqual(context, {"input_ref": "lap://run/input/invoice"})
        self.assertEqual(admission.release, self.expected)
        self.assertEqual(self.gate.expected_release, self.expected)

        payload = admission.release.payload()
        payload["capability_contracts"]["invoice.extract"] = OTHER_DIGEST
        self.assertEqual(
            admission.release.capability_contracts["invoice.extract"], CAPABILITY_DIGEST
        )

    def test_identity_component_mismatches_are_deterministic_and_safe(self) -> None:
        """Identify components for Host audit without exposing actual digest values."""
        running = release_payload()
        running["agent_id"] = "io.example.other-agent"
        running["version"] = "2.0.1"
        running["package_digest"] = OTHER_DIGEST
        running["manifest_digest"] = OTHER_DIGEST

        with self.assertRaises(ContractMismatchError) as raised:
            self.gate.verify(running)

        self.assertEqual(
            raised.exception.fields,
            ("agent_id", "version", "package_digest", "manifest_digest"),
        )
        self.assertNotIn(OTHER_DIGEST, str(raised.exception))

    def test_malformed_identity_and_invalid_direct_values_are_rejected(self) -> None:
        """Reject malformed wire values and invalid public value construction."""
        invalid_payloads: list[dict[str, Any]] = []

        missing = release_payload()
        del missing["version"]
        invalid_payloads.append(missing)

        extra = release_payload()
        extra["unexpected"] = True
        invalid_payloads.append(extra)

        invalid_digest = release_payload()
        invalid_digest["package_digest"] = "sha256:" + "A" * 64
        invalid_payloads.append(invalid_digest)

        no_capabilities = release_payload()
        no_capabilities["capability_contracts"] = {}
        invalid_payloads.append(no_capabilities)

        non_object_capabilities = release_payload()
        non_object_capabilities["capability_contracts"] = ["not-an-object"]
        invalid_payloads.append(non_object_capabilities)

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ContractValidationError):
                    ReleaseIdentity.from_payload(payload)

        with self.assertRaises(ContractValidationError):
            ReleaseIdentity(
                "io.example.agent",
                "2.0.0",
                PACKAGE_DIGEST,
                MANIFEST_DIGEST,
                (
                    ("invoice.validate", OTHER_DIGEST),
                    ("invoice.extract", CAPABILITY_DIGEST),
                ),
            )
        with self.assertRaises(ContractValidationError):
            ContractGate(cast(ReleaseIdentity, "not-a-release"))
        with self.assertRaises(ContractValidationError):
            self.gate.admit(
                self.expected,
                cast(Callable[[], dict[str, str]], "not-a-supplier"),
            )


if __name__ == "__main__":
    unittest.main()
