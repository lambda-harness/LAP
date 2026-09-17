"""Check isolated Core 0.2 schema and registry invariants."""

import json
import unittest
from pathlib import Path


class Core02SchemaTests(unittest.TestCase):
    """Protect registry completeness without requiring runtime activation."""

    def test_registry_matches_envelope(self):
        root = Path(__file__).resolve().parents[1] / "schemas" / "core-0.2"
        envelope = json.loads((root / "envelope.schema.json").read_text())
        registry = json.loads((root / "registry.json").read_text())
        types = [item["type"] for item in registry["messages"]]
        self.assertEqual(len(types), len(set(types)))
        self.assertEqual(set(types), set(envelope["properties"]["type"]["enum"]))
        self.assertTrue(all(item["schema_status"] == "draft" for item in registry["messages"]))
        self.assertEqual(envelope["properties"]["lap"]["const"], "0.2")
        for field in ("stream_id", "epoch", "seq"):
            self.assertIn(field, envelope["required"])
        self.assertEqual(envelope["properties"]["epoch"]["minimum"], 1)
        self.assertEqual(envelope["properties"]["seq"]["minimum"], 1)

    def test_core_01_unchanged(self):
        root = Path(__file__).resolve().parents[1] / "schemas"
        envelope = json.loads((root / "envelope.schema.json").read_text())
        self.assertEqual(envelope["properties"]["lap"]["const"], "0.1")
        self.assertNotIn("stream_id", envelope["required"])


if __name__ == "__main__":
    unittest.main()
