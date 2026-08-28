"""Smoke conformance checks for the published LAP 0.1 examples."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[1]
CHECKER = FormatChecker()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_name: str, value: object) -> None:
    schema = load_json(ROOT / "schemas" / schema_name)
    Draft202012Validator(schema, format_checker=CHECKER).validate(value)


class ExampleConformanceTests(unittest.TestCase):
    def test_every_readme_has_a_chinese_counterpart(self) -> None:
        readmes = sorted(ROOT.rglob("README.md"))
        self.assertTrue(readmes)
        missing = [str(path.relative_to(ROOT)) for path in readmes
                   if not path.with_name("README.zh-CN.md").is_file()]
        self.assertEqual(missing, [])

    def test_manifest_and_workflow_examples_validate(self) -> None:
        validate("agent-manifest.schema.json", load_json(ROOT / "examples" / "echo-agent" / "agent.json"))
        validate("agent-manifest.schema.json", load_json(ROOT / "examples" / "echo-agent-go" / "agent.json"))
        validate("agent-manifest.schema.json", load_json(ROOT / "examples" / "echo-agent-rust" / "agent.json"))
        validate("workflow.schema.json", load_json(ROOT / "examples" / "release-check.workflow.json"))

    def test_workflow_parallel_bound_is_optional_but_positive(self) -> None:
        workflow = load_json(ROOT / "examples" / "release-check.workflow.json")
        workflow["policy"]["max_parallel_nodes"] = 2
        validate("workflow.schema.json", workflow)
        workflow["policy"]["max_parallel_nodes"] = 0
        with self.assertRaises(ValidationError):
            validate("workflow.schema.json", workflow)

    def test_context_packet_and_result_validate(self) -> None:
        validate("context-packet.schema.json", {
            "input": {"text": "hello LAP"},
            "deadline_at": "2026-08-26T12:00:00Z",
            "budget": {"max_output_tokens": 128, "max_child_runs": 0},
        })
        validate("run-result.schema.json", {
            "status": "failed",
            "summary": "Agent exited before producing a result.",
            "error": {"code": "LAP-500", "message": "Unexpected process exit.", "retryable": True},
        })

    def test_manifest_integrity_pairs_digest_with_a_package_relative_target(self) -> None:
        manifest = load_json(ROOT / "examples" / "echo-agent" / "agent.json")
        self.assertIsInstance(manifest, dict)
        manifest["integrity"] = {"sha256": "0" * 64}
        with self.assertRaises(ValidationError):
            validate("agent-manifest.schema.json", manifest)

        manifest["integrity"] = {"path": "echo_agent.py", "sha256": "0" * 64}
        validate("agent-manifest.schema.json", manifest)

    def test_local_echo_agent_negotiates_and_returns_a_valid_result(self) -> None:
        frames = "\n".join([
            json.dumps({
                "lap": "0.1", "id": "host-1", "producer": "host.test", "seq": 1,
                "type": "agent.hello", "payload": {},
            }),
            json.dumps({
                "lap": "0.1", "id": "host-2", "producer": "host.test", "seq": 2,
                "type": "run.start",
                "run": {
                    "tenant_id": "tenant-demo", "session_id": "session-demo",
                    "run_id": "run-demo", "trace_id": "trace-demo",
                },
                "idempotency_key": "demo-key",
                "payload": {"capability": "text.echo", "input": {"text": "hello LAP"}},
            }),
            json.dumps({
                "lap": "0.1", "id": "host-3", "producer": "host.test", "seq": 3,
                "type": "agent.shutdown", "payload": {},
            }),
        ]) + "\n"
        completed = subprocess.run(
            [sys.executable, "echo_agent.py"],
            cwd=ROOT / "examples" / "echo-agent",
            input=frames,
            text=True,
            capture_output=True,
            check=True,
        )
        outputs = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([item["type"] for item in outputs], [
            "agent.welcome", "run.accepted", "run.progress", "run.result",
        ])
        for output in outputs:
            validate("envelope.schema.json", output)
        validate("run-result.schema.json", outputs[-1]["payload"])
        self.assertEqual(outputs[-1]["payload"]["output"], {"text": "hello LAP"})


if __name__ == "__main__":
    unittest.main()
