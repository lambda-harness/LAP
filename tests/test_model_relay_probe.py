"""Black-box checks for the draft LAP Model Relay author-side probe."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "lap_model_relay_probe.py"
REFERENCE_PACKAGE = ROOT / "examples" / "model-relay-agent"


class ModelRelayProbeTests(unittest.TestCase):
    def _invoke(
        self, package: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROBE), "--package", str(package), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def test_runs_the_published_draft_reference_without_a_provider_call(self) -> None:
        completed = self._invoke(REFERENCE_PACKAGE)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["valid"])
        self.assertEqual(report["suite"], "lap-model-relay-probe/0.1-draft")
        self.assertEqual(report["profile"], "lap-model-relay/0.1")
        self.assertEqual(
            report["agent"],
            {
                "id": "org.lap.model-relay-agent",
                "version": "0.1.0",
                "capability": "text.summarize_via_host",
            },
        )
        self.assertEqual(
            report["relay"],
            {
                "route": "host.default",
                "response": "deterministic-host-simulation",
                "provider_calls": 0,
            },
        )
        self.assertEqual(
            report["frames"]["types"],
            [
                "agent.welcome",
                "run.accepted",
                "run.progress",
                "model.request",
                "run.progress",
                "run.result",
            ],
        )
        self.assertNotIn("LAP Local conformance probe", completed.stdout)
        self.assertNotIn("Relay probe response.", completed.stdout)

    def test_accepts_explicit_capability_json_without_exposing_it_in_the_report(
        self,
    ) -> None:
        completed = self._invoke(
            REFERENCE_PACKAGE, "--input", '{"text":"Tenant-specific probe input"}'
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Tenant-specific probe input", completed.stdout)

    def test_rejects_a_package_that_does_not_declare_the_draft_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "model-relay-agent"
            shutil.copytree(REFERENCE_PACKAGE, package)
            manifest_path = package / "agent.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["profiles"] = ["lap-local/0.1"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = self._invoke(package)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stderr)["error"]["code"], "LAP-204")


if __name__ == "__main__":
    unittest.main()
