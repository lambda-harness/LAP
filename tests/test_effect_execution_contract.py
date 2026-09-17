"""Validate the portable draft ``lap-effect/0.1`` Schema and vector."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    """Load one checked JSON object from the repository."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}.")
    return cast(dict[str, Any], value)


class EffectExecutionContractTests(unittest.TestCase):
    """Keep the draft Profile's payload fragments and lifecycle vector aligned."""

    def setUp(self) -> None:
        """Load the public Schema and deterministic Profile vector."""
        self.schema = load_json(ROOT / "schemas" / "effect-execution-0.1.schema.json")
        self.vector = load_json(ROOT / "conformance" / "effect-execution.json")

    def test_schema_accepts_and_rejects_declared_profile_payloads(self) -> None:
        """Validate every published positive and negative profile payload vector."""
        Draft202012Validator.check_schema(self.schema)
        definitions = self.schema["$defs"]
        for case in self.vector["valid_payloads"]:
            with self.subTest(fragment=case["fragment"], valid=True):
                validator = Draft202012Validator(
                    {"$defs": definitions, "$ref": f"#/$defs/{case['fragment']}"}
                )
                self.assertEqual(list(validator.iter_errors(case["value"])), [])
        for case in self.vector["invalid_payloads"]:
            with self.subTest(fragment=case["fragment"], valid=False):
                validator = Draft202012Validator(
                    {"$defs": definitions, "$ref": f"#/$defs/{case['fragment']}"}
                )
                self.assertNotEqual(list(validator.iter_errors(case["value"])), [])

    def test_vector_preserves_truthful_effect_lifecycle_and_rejections(self) -> None:
        """Keep acceptance, settlement, reconciliation, and policy gates distinct."""
        self.assertEqual(self.vector["profile"], "lap-effect/0.1")
        self.assertEqual(self.vector["status"], "draft")
        self.assertEqual(
            self.vector["required_effect_lifecycle"],
            [
                "proposed",
                "approval_required",
                "authorized",
                "accepted",
                "unknown",
                "reconciling",
                "indeterminate",
            ],
        )
        rejections = self.vector["required_rejections"]
        self.assertEqual(
            {item["code"] for item in rejections},
            {"LAP-201", "LAP-301", "LAP-104", "LAP-109"},
        )
        self.assertTrue(all(item["provider_contacted"] is False for item in rejections))


if __name__ == "__main__":
    unittest.main()
