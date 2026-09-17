"""Check draft Core 0.2 typed-wire and state-machine invariants."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CHECKER = FormatChecker()


def load_json(path: Path) -> dict[str, Any]:
    """Load one checked JSON object from the repository."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}.")
    return cast(dict[str, Any], value)


class Core02SchemaTests(unittest.TestCase):
    """Protect draft Core 0.2 without enabling the Core 0.1 runtime path."""

    def setUp(self) -> None:
        self.root = ROOT / "schemas" / "core-0.2"
        self.envelope = load_json(self.root / "envelope.schema.json")
        self.registry = load_json(self.root / "registry.json")
        self.registry_schema = load_json(self.root / "message-registry.json")
        self.state_machine = load_json(self.root / "state-machine.json")
        self.vector = load_json(ROOT / "conformance" / "core-0.2-wire.json")

    def test_registry_matches_envelope_and_payload_contracts(self) -> None:
        Draft202012Validator.check_schema(self.envelope)
        Draft202012Validator.check_schema(self.registry_schema)
        Draft202012Validator(self.registry_schema).validate(self.registry)

        types = [item["type"] for item in self.registry["messages"]]
        self.assertEqual(len(types), len(set(types)))
        self.assertEqual(set(types), set(self.envelope["properties"]["type"]["enum"]))
        self.assertTrue(
            all(item["schema_status"] == "draft" for item in self.registry["messages"])
        )
        self.assertEqual(self.envelope["properties"]["lap"]["const"], "0.2")
        self.assertEqual(self.registry["state_machine"], "state-machine.json")

        for field in ("sender", "stream_id", "epoch", "seq"):
            self.assertIn(field, self.envelope["required"])
        self.assertEqual(self.envelope["properties"]["epoch"]["minimum"], 1)
        self.assertEqual(self.envelope["properties"]["seq"]["minimum"], 1)

        payload_defs = self.envelope["$defs"]
        for message in self.registry["messages"]:
            fragment = message["payload_schema"].removeprefix(
                "envelope.schema.json#/$defs/"
            )
            self.assertIn(fragment, payload_defs)
            self.assertTrue(fragment.endswith("_payload"))

    def test_state_machine_covers_every_registered_message(self) -> None:
        registry_by_type = {
            item["type"]: item["sender"] for item in self.registry["messages"]
        }
        declared_events: list[dict[str, Any]] = []
        for scope in ("activation", "run", "stream"):
            machine = self.state_machine[scope]
            declared_events.extend(machine["events"])
            states = set(machine.get("states", []))
            for event in machine["events"]:
                self.assertEqual(event["sender"], registry_by_type[event["type"]])
                self.assertTrue(set(event["from"]).issubset(states))
                if event["to"] not in {"$same", "$terminal_from_payload"}:
                    self.assertIn(event["to"], states)

        self.assertEqual(
            {event["type"] for event in declared_events}, set(registry_by_type)
        )

        run = self.state_machine["run"]
        terminal = set(run["terminal"])
        self.assertTrue(terminal.issubset(set(run["states"])))
        for event in run["events"]:
            if terminal.intersection(event["from"]):
                self.assertEqual(event["to"], "$same")

        stream_ack = next(
            event
            for event in self.state_machine["stream"]["events"]
            if event["type"] == "stream.ack"
        )
        self.assertFalse(stream_ack["ack_of_ack"])

    def test_positive_and_negative_wire_vectors(self) -> None:
        validator = Draft202012Validator(self.envelope, format_checker=CHECKER)
        valid_cases = {case["id"]: case for case in self.vector["valid_cases"]}
        registry_types = {item["type"] for item in self.registry["messages"]}
        self.assertEqual(
            {case["type"] for case in valid_cases.values()}, registry_types
        )

        for sequence, case in enumerate(valid_cases.values(), start=1):
            with self.subTest(case=case["id"]):
                validator.validate(self._materialize(case, sequence))

        for negative in self.vector["negative_cases"]:
            with self.subTest(case=negative["id"]):
                source = valid_cases[negative["valid_case"]]
                frame = self._materialize(source, 100)
                key = negative["path"].removeprefix("/")
                if negative.get("delete"):
                    del frame[key]
                else:
                    frame[key] = deepcopy(negative["value"])
                with self.assertRaises(ValidationError):
                    validator.validate(frame)

    def test_core_01_unchanged(self) -> None:
        envelope = load_json(ROOT / "schemas" / "envelope.schema.json")
        self.assertEqual(envelope["properties"]["lap"]["const"], "0.1")
        self.assertNotIn("stream_id", envelope["required"])
        self.assertNotIn("sender", envelope["required"])

    def _materialize(self, case: dict[str, Any], sequence: int) -> dict[str, Any]:
        defaults = self.vector["defaults"]
        frame: dict[str, Any] = {
            "lap": "0.2",
            "id": f"event-{case['id'].lower()}",
            "producer": f"{case['sender']}.fixture",
            "sender": case["sender"],
            "stream_id": defaults["stream_id"],
            "epoch": 1,
            "seq": sequence,
            "occurred_at": defaults["occurred_at"],
            "type": case["type"],
            "payload": deepcopy(case["payload"]),
        }
        if case.get("run"):
            frame["run"] = deepcopy(defaults["run"])
        if case.get("correlation"):
            frame["correlation_id"] = f"request-{case['id'].lower()}"
        if case.get("idempotency"):
            frame["idempotency_key"] = f"idempotency-{case['id'].lower()}"
        if "ack_seq" in case:
            frame["ack_seq"] = case["ack_seq"]
        return frame


if __name__ == "__main__":
    unittest.main()
