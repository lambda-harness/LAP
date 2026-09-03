"""Black-box checks for the public LAP Local Agent probe CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "lap_local_probe.py"


def _write_agent(package: Path, *, invalid_output: bool = False) -> None:
    package.mkdir()
    agent_id = "com.example.probe-agent"
    package.joinpath("agent.json").write_text(
        json.dumps(
            {
                "lap": "0.1",
                "protocol_versions": ["0.1"],
                "profiles": ["lap-local/0.1"],
                "id": agent_id,
                "display_name": "Probe Agent",
                "version": "1.0.0",
                "description": "A local probe fixture.",
                "transport": {
                    "kind": "lap-local",
                    "command": [sys.executable, "agent.py"],
                    "working_directory": ".",
                },
                "capabilities": [
                    {
                        "id": "ticket.execute",
                        "description": "Returns a ticket identifier.",
                        "input_schema": {
                            "type": "object",
                            "required": ["ticket"],
                            "properties": {"ticket": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        "output_schema": {
                            "type": "object",
                            "required": ["ticket"],
                            "properties": {"ticket": {"type": "string"}},
                            "additionalProperties": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = '{"wrong": "value"}' if invalid_output else '{"ticket": ticket}'
    package.joinpath("agent.py").write_text(
        textwrap.dedent(f"""\
        import json
        from pathlib import Path
        import sys

        AGENT_ID = {agent_id!r}
        sequence = 0
        Path("started.txt").write_text("started", encoding="utf-8")

        def emit(message_type, payload, correlation_id=None, run=None):
            global sequence
            sequence += 1
            frame = {{
                "lap": "0.1", "id": f"probe-{{sequence}}", "producer": AGENT_ID,
                "seq": sequence, "type": message_type, "payload": payload,
            }}
            if correlation_id:
                frame["correlation_id"] = correlation_id
            if run:
                frame["run"] = run
            print(json.dumps(frame, separators=(",", ":")), flush=True)

        for raw in sys.stdin:
            frame = json.loads(raw)
            if frame.get("type") == "agent.hello":
                emit("agent.welcome", {{
                    "selected_lap": "0.1", "profiles": ["lap-local/0.1"],
                    "agent_id": AGENT_ID, "version": "1.0.0", "max_concurrency": 1,
                }}, correlation_id=frame["id"])
            elif frame.get("type") == "run.start":
                run = frame["run"]
                ticket = frame["payload"]["input"]["ticket"]
                emit("run.accepted", {{"capability": frame["payload"]["capability"]}}, correlation_id=frame["id"], run=run)
                emit("run.progress", {{"phase": "ticket", "message": "Validated ticket."}}, run=run)
                emit("run.result", {{"status": "succeeded", "summary": "Ticket complete.", "output": {output}}}, run=run)
            elif frame.get("type") == "agent.shutdown":
                break
    """),
        encoding="utf-8",
    )


class LocalProbeTests(unittest.TestCase):
    def _invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROBE), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def test_runs_the_published_python_reference_with_its_declared_command(
        self,
    ) -> None:
        completed = self._invoke("--package", str(ROOT / "examples" / "echo-agent"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["agent"],
            {
                "id": "org.lap.echo-agent",
                "version": "0.1.0",
                "capability": "text.echo",
            },
        )
        self.assertEqual(
            report["frames"]["types"],
            [
                "agent.welcome",
                "run.accepted",
                "run.progress",
                "run.result",
            ],
        )
        self.assertEqual(
            report["terminal"], {"status": "succeeded", "output_contract": "validated"}
        )

    def test_accepts_explicit_json_for_an_arbitrary_declared_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "probe-agent"
            _write_agent(package)
            completed = self._invoke(
                "--package",
                str(package),
                "--capability",
                "ticket.execute",
                "--input",
                '{"ticket":"OPS-17"}',
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["valid"])
        self.assertEqual(report["agent"]["capability"], "ticket.execute")
        self.assertNotIn("OPS-17", completed.stdout)

    def test_rejects_an_invalid_probe_input_before_starting_the_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "probe-agent"
            _write_agent(package)
            completed = self._invoke(
                "--package", str(package), "--capability", "ticket.execute"
            )
            self.assertFalse((package / "started.txt").exists())

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], "LAP-201")

    def test_rejects_a_successful_terminal_output_that_breaks_the_manifest_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "probe-agent"
            _write_agent(package, invalid_output=True)
            completed = self._invoke(
                "--package",
                str(package),
                "--capability",
                "ticket.execute",
                "--input",
                '{"ticket":"OPS-17"}',
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], "LAP-101")


if __name__ == "__main__":
    unittest.main()
