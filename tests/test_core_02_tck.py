"""Protect the draft Core 0.2 TCK registry and claim boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ASSERTION_IDS = frozenset(
    (
        "C02-WIRE-01",
        "C02-CONTRACT-01",
        "C02-STREAM-01",
        "C02-STREAM-02",
        "C02-STREAM-03",
        "C02-RESUME-01",
        "C02-ART-01",
        "C02-ART-02",
        "C02-ART-03",
        "C02-RUN-01",
        "C02-RUN-02",
        "C02-ERR-01",
        "C02-SEC-01",
    )
)
REFERENCE_ASSERTION_IDS = frozenset(
    (
        "C02-STREAM-01",
        "C02-STREAM-02",
        "C02-STREAM-03",
        "C02-RESUME-01",
        "C02-ART-01",
        "C02-ART-02",
        "C02-ART-03",
        "C02-RUN-01",
        "C02-RUN-02",
        "C02-ERR-01",
        "C02-SEC-01",
    )
)


def load_json(path: Path) -> dict[str, Any]:
    """Load one checked JSON object from the repository."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}.")
    return cast(dict[str, Any], value)


class Core02TckTests(unittest.TestCase):
    """Keep draft evidence distinct from a production conformance claim."""

    def setUp(self) -> None:
        self.schema = load_json(
            ROOT / "schemas" / "core-0.2" / "tck-registry.schema.json"
        )
        self.registry = load_json(ROOT / "conformance" / "core-0.2-tck.json")
        self.spec = (ROOT / "docs" / "core-0.2-spec.md").read_text(encoding="utf-8")

    def test_registry_is_complete_and_not_claimable(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.registry)

        assertions = self.registry["assertions"]
        identifiers = [assertion["id"] for assertion in assertions]
        self.assertEqual(set(identifiers), EXPECTED_ASSERTION_IDS)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(self.registry["claimability"]["status"], "not_claimable")
        self.assertGreaterEqual(len(self.registry["claimability"]["blockers"]), 3)

        verified = {
            assertion["id"]
            for assertion in assertions
            if assertion["status"] == "verified_draft"
        }
        self.assertEqual(verified, {"C02-WIRE-01"})
        self.assertEqual(
            {
                assertion["id"]
                for assertion in assertions
                if assertion["status"] == "pending_runtime"
            },
            EXPECTED_ASSERTION_IDS - verified,
        )

    def test_assertions_link_to_spec_and_evidence_state(self) -> None:
        for assertion in self.registry["assertions"]:
            with self.subTest(assertion=assertion["id"]):
                self.assertIn(f"| {assertion['id']} |", self.spec)
                verification = assertion["verification"]
                if assertion["status"] == "verified_draft":
                    self.assertEqual(verification["status"], "verified")
                    self.assertTrue((ROOT / verification["location"]).is_file())
                    test_path = verification["test"].split("::", maxsplit=1)[0]
                    self.assertTrue((ROOT / test_path).is_file())
                else:
                    self.assertEqual(verification["status"], "planned")
                    self.assertIn("scenario", verification)
                    self.assertNotIn("location", verification)
                    self.assertNotIn("test", verification)
                reference = assertion.get("reference_evidence")
                if assertion["id"] in REFERENCE_ASSERTION_IDS:
                    self.assertIsNotNone(reference)
                    assert reference is not None
                    self.assertEqual(reference["kind"], "state-machine-test")
                    self.assertTrue((ROOT / reference["location"]).is_file())
                    test_path = reference["test"].split("::", maxsplit=1)[0]
                    self.assertTrue((ROOT / test_path).is_file())
                    self.assertIn("reference", reference["limitations"].lower())
                else:
                    self.assertIsNone(reference)


if __name__ == "__main__":
    unittest.main()
