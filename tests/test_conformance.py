"""Portable LAP 0.1 contract checks and the published local round trip."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
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


def ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


class ConformanceKitTests(unittest.TestCase):
    def test_a2a_inline_input_vector_requires_three_gates_and_preserves_exact_bytes(self) -> None:
        vector = load_json(ROOT / "conformance" / "a2a-inline-inputs.json")
        self.assertIsInstance(vector, dict)
        self.assertEqual(vector["profile"], "lap-a2a-inline-inputs/0.1")
        self.assertEqual(vector["a2a_version"], "0.3.0")
        self.assertTrue(vector["host_policy"]["allow_inline_input_artifacts"])
        self.assertGreater(vector["host_policy"]["max_request_bytes"], 0)

        transport = vector["manifest_transport"]
        validate("agent-manifest.schema.json", {
            "lap": "0.1",
            "id": "org.lap.remote-workbook",
            "display_name": "Remote workbook",
            "version": "0.1.0",
            "transport": transport,
            "capabilities": [{
                "id": "workbook.inspect",
                "description": "Inspect an approved workbook.",
            }],
        })
        self.assertEqual(transport["input_artifact_transfer"], "inline")

        artifact = vector["input_artifact"]
        decoded = base64.b64decode(artifact["bytes_base64"], validate=True)
        self.assertEqual(len(decoded), artifact["size_bytes"])
        self.assertEqual(hashlib.sha256(decoded).hexdigest(), artifact["sha256"])
        self.assertIn(artifact["media_type"], vector["selected_skill"]["input_modes"])

        part = vector["expected_file_part"]
        self.assertEqual(part["kind"], "file")
        self.assertNotIn("uri", part["file"])
        self.assertEqual(part["file"]["bytes"], artifact["bytes_base64"])
        self.assertEqual(part["file"]["name"], artifact["name"])
        self.assertEqual(part["file"]["mimeType"], artifact["media_type"])
        metadata = part["metadata"]["io.github.dongrv.lap.a2a.inline-inputs"]
        self.assertEqual(metadata, {
            "id": artifact["id"],
            "sha256": artifact["sha256"],
            "sizeBytes": artifact["size_bytes"],
        })

        failures = {item["case"]: item for item in vector["required_rejections"]}
        self.assertEqual(set(failures), {
            "host policy disabled",
            "manifest omitted inline opt-in",
            "selected skill MIME mismatch",
            "source digest changed before transfer",
            "serialized request exceeds Host bound",
        })
        self.assertEqual(failures["host policy disabled"]["code"], "LAP-402")
        self.assertEqual(failures["manifest omitted inline opt-in"]["code"], "LAP-402")
        self.assertEqual(failures["selected skill MIME mismatch"]["code"], "LAP-402")
        self.assertEqual(failures["source digest changed before transfer"]["code"], "LAP-409")
        self.assertEqual(failures["serialized request exceeds Host bound"]["code"], "LAP-401")
        self.assertTrue(all(item["remote_task_created"] is False for item in failures.values()))

    def test_workflow_budget_vector_defines_explicit_static_and_dynamic_allocations(self) -> None:
        vector = load_json(ROOT / "conformance" / "workflow-budget.json")
        self.assertIsInstance(vector, dict)
        workflow = vector["strict_output_budget_workflow"]
        validate("workflow.schema.json", workflow)
        policy = workflow["policy"]
        allocations = [node["budget"]["max_output_tokens"] for node in workflow["nodes"]]
        self.assertLessEqual(sum(allocations), policy["max_output_tokens"])
        proposal = vector["dynamic_dispatch"]
        self.assertEqual(set(proposal), {"agent_id", "capability", "input", "budget"})
        self.assertIsInstance(proposal["budget"]["max_output_tokens"], int)

        zero_allocation = json.loads(json.dumps(workflow))
        zero_allocation["nodes"][0]["budget"]["max_output_tokens"] = 0
        with self.assertRaises(ValidationError):
            validate("workflow.schema.json", zero_allocation)

        oversubscribed = vector["oversubscribed_static_allocations"]
        validate("workflow.schema.json", oversubscribed)
        invalid_allocations = [node["budget"]["max_output_tokens"] for node in oversubscribed["nodes"]]
        self.assertGreater(sum(invalid_allocations), oversubscribed["policy"]["max_output_tokens"])

    def test_workflow_release_admission_vector_scopes_a_draining_release_to_one_root(self) -> None:
        vector = load_json(ROOT / "conformance" / "workflow-release-admission.json")
        self.assertIsInstance(vector, dict)
        self.assertEqual(vector["profile"], "lap-workflow/0.1")
        root = vector["root"]
        self.assertEqual(set(root), {"tenant_id", "session_id", "workflow_run_id", "release"})
        self.assertTrue(root["tenant_id"])
        self.assertTrue(root["session_id"])
        self.assertTrue(root["workflow_run_id"])
        self.assertEqual(root["release"]["agent_id"], "com.example.inspector")
        self.assertRegex(root["release"]["release_identity"], r"^sha256:[a-f0-9]{64}$")

        admission = vector["admission"]
        self.assertEqual(admission, {
            "host_private": True,
            "serialized_to_agent": False,
            "invalidated_on_root_terminal": True,
        })
        accepted = vector["accepted_child"]
        self.assertEqual(accepted["tenant_id"], root["tenant_id"])
        self.assertEqual(accepted["session_id"], root["session_id"])
        self.assertEqual(accepted["parent_run_id"], root["workflow_run_id"])
        self.assertTrue(accepted["agent_started"])

        rejections = {item["case"]: item for item in vector["required_rejections"]}
        self.assertEqual(set(rejections), {
            "new root after release begins draining",
            "tenant mismatch",
            "session mismatch",
            "root run mismatch",
            "closed admission",
            "fabricated admission",
        })
        self.assertTrue(all(item["agent_started"] is False for item in rejections.values()))
        self.assertEqual(rejections["tenant mismatch"]["tenant_id"], "tenant-other")
        self.assertEqual(rejections["session mismatch"]["session_id"], "session-other")
        self.assertEqual(rejections["root run mismatch"]["parent_run_id"], "workflow-other")
        self.assertEqual(rejections["closed admission"]["admission"], "closed")
        self.assertEqual(rejections["fabricated admission"]["admission"], "fabricated")

    def test_host_metering_vector_uses_integer_reservation_and_conservative_fallback(self) -> None:
        vector = load_json(ROOT / "conformance" / "host-metering.json")
        self.assertIsInstance(vector, dict)
        self.assertEqual(vector["profile"], "lap-host-metering/0.1")
        self.assertEqual(vector["currency"], "USD")
        prices = vector["prices_microunits_per_million"]
        reservation = vector["reservation"]
        denominator = 1_000_000

        def cost(input_tokens: int, cached_tokens: int, output_tokens: int) -> int:
            cached = min(max(0, input_tokens), max(0, cached_tokens))
            return (
                ceil_div((input_tokens - cached) * prices["input"], denominator)
                + ceil_div(cached * prices["cached_input"], denominator)
                + ceil_div(output_tokens * prices["output"], denominator)
            )

        reserved = (
            ceil_div(
                reservation["input_upper_bound_tokens"]
                * max(prices["input"], prices["cached_input"]),
                denominator,
            )
            + ceil_div(
                reservation["output_upper_bound_tokens"] * prices["output"],
                denominator,
            )
        )
        self.assertEqual(reserved, reservation["expected_cost_microunits"])

        settlement = vector["settlement"]
        observed = settlement["provider_usage"]
        self.assertEqual(
            cost(observed["input_tokens"], observed["cached_tokens"], observed["output_tokens"]),
            settlement["expected_cost_microunits"],
        )

        fallback = vector["missing_usage_settlement"]
        self.assertEqual(
            cost(fallback["expected_input_tokens"], 0, fallback["expected_output_tokens"]),
            fallback["expected_cost_microunits"],
        )
        self.assertEqual(fallback["expected_cost_microunits"], reserved)

    def test_workflow_capability_scopes_vector_is_exact_and_pre_dispatch(self) -> None:
        vector = load_json(ROOT / "conformance" / "workflow-capability-scopes.json")
        self.assertIsInstance(vector, dict)
        self.assertEqual(vector["profile"], "lap-workflow/0.1")
        workflow = vector["workflow"]
        validate("workflow.schema.json", workflow)
        node = workflow["nodes"][0]
        allowed = set(node["allowed_agent_ids"])
        scopes = node["allowed_capabilities"]
        self.assertEqual(set(scopes), allowed)
        self.assertTrue(all(values and len(values) == len(set(values)) for values in scopes.values()))

        admitted = vector["admitted_capabilities"]
        accepted = vector["accepted_dispatch"]
        self.assertIn(accepted["agent_id"], allowed)
        self.assertIn(accepted["capability"], scopes[accepted["agent_id"]])
        self.assertIn(accepted["capability"], admitted[accepted["agent_id"]])
        self.assertTrue(accepted["target_agent_started"])

        rejections = {item["case"]: item for item in vector["required_rejections"]}
        self.assertEqual(set(rejections), {
            "Agent outside immutable allowlist",
            "Declared capability outside scoped mapping",
            "Undeclared capability",
        })
        self.assertTrue(all(item["code"] == "LAP-301" for item in rejections.values()))
        self.assertTrue(all(item["target_agent_started"] is False for item in rejections.values()))
        self.assertNotIn(rejections["Agent outside immutable allowlist"]["proposal"]["agent_id"], allowed)
        scoped_out = rejections["Declared capability outside scoped mapping"]["proposal"]
        self.assertIn(scoped_out["agent_id"], allowed)
        self.assertNotIn(scoped_out["capability"], scopes[scoped_out["agent_id"]])
        self.assertIn(scoped_out["capability"], admitted[scoped_out["agent_id"]])
        undeclared = rejections["Undeclared capability"]["proposal"]
        self.assertNotIn(undeclared["capability"], admitted[undeclared["agent_id"]])

        for rejection in vector["document_rejections"]:
            self.assertNotEqual(set(rejection["allowed_capabilities"]), allowed)

        invalid = json.loads(json.dumps(workflow))
        invalid["nodes"][0]["allowed_capabilities"]["com.example.inspector"] = []
        with self.assertRaises(ValidationError):
            validate("workflow.schema.json", invalid)

    def test_capability_contract_vector_has_distinct_valid_and_invalid_instances(self) -> None:
        vector = load_json(ROOT / "conformance" / "capability-contract.json")
        self.assertIsInstance(vector, dict)
        self.assertEqual(vector["lap"], "0.1")
        self.assertEqual(vector["schema_draft"], "https://json-schema.org/draft/2020-12/schema")
        capability = vector["capability"]
        self.assertIsInstance(capability, dict)
        for field, valid_key, invalid_key in (
            ("input_schema", "valid_input", "invalid_input"),
            ("output_schema", "valid_output", "invalid_output"),
        ):
            schema = capability[field]
            self.assertIsInstance(schema, dict)
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            validator.validate(vector[valid_key])
            with self.assertRaises(ValidationError):
                validator.validate(vector[invalid_key])

    def _assert_local_roundtrip(self, command: list[str], directory: Path, *,
                                agent_id: str, version: str) -> None:
        vector = load_json(ROOT / "conformance" / "local-stdio-roundtrip.json")
        self.assertIsInstance(vector, dict)
        host_frames = vector["host_frames"]
        expected = vector["expect"]
        self.assertEqual(vector["profile"], "lap-local/0.1")
        self.assertEqual([frame["seq"] for frame in host_frames], [1, 2, 3])
        for frame in host_frames:
            validate("envelope.schema.json", frame)
        context = host_frames[1]["payload"]["context"]
        validate("context-packet.schema.json", context)
        artifact = context["artifacts"][0]
        self.assertTrue(artifact["uri"].startswith("lap://run/input/"))
        self.assertEqual(len(artifact["sha256"]), 64)

        completed = subprocess.run(
            command,
            cwd=directory,
            input="\n".join(json.dumps(frame) for frame in host_frames) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
        outputs = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([frame["type"] for frame in outputs], expected["agent_types"])
        self.assertEqual([frame["seq"] for frame in outputs], list(range(1, len(outputs) + 1)))
        self.assertEqual(len({frame["id"] for frame in outputs}), len(outputs))
        for frame in outputs:
            validate("envelope.schema.json", frame)

        welcome = outputs[0]
        self.assertEqual(welcome["correlation_id"], host_frames[0]["id"])
        self.assertEqual(welcome["payload"]["selected_lap"], expected["selected_lap"])
        self.assertIn(expected["profile"], welcome["payload"]["profiles"])
        self.assertEqual(welcome["producer"], agent_id)
        self.assertTrue(all(frame["producer"] == agent_id for frame in outputs))
        self.assertEqual(welcome["payload"]["agent_id"], agent_id)
        self.assertEqual(welcome["payload"]["version"], version)

        run = host_frames[1]["run"]
        accepted, progress, result = outputs[1:]
        self.assertEqual(accepted["correlation_id"], host_frames[1]["id"])
        self.assertEqual(accepted["run"], run)
        self.assertEqual(progress["run"], run)
        self.assertEqual(result["run"], run)
        validate("run-result.schema.json", result["payload"])
        self.assertEqual(result["payload"], expected["result"])

    def test_local_roundtrip_vector_runs_the_python_reference_agent(self) -> None:
        self._assert_local_roundtrip(
            [sys.executable, "echo_agent.py"],
            ROOT / "examples" / "echo-agent",
            agent_id="org.lap.echo-agent",
            version="0.1.0",
        )

    @unittest.skipUnless(shutil.which("go"), "Go toolchain is not installed")
    def test_local_roundtrip_vector_runs_the_go_reference_agent(self) -> None:
        self._assert_local_roundtrip(
            ["go", "run", "."],
            ROOT / "examples" / "echo-agent-go",
            agent_id="org.lap.go-echo-agent",
            version="0.1.0",
        )

    @unittest.skipUnless(shutil.which("cargo"), "Rust toolchain is not installed")
    def test_local_roundtrip_vector_runs_the_rust_reference_agent(self) -> None:
        self._assert_local_roundtrip(
            ["cargo", "run", "--quiet"],
            ROOT / "examples" / "echo-agent-rust",
            agent_id="org.lap.rust-echo-agent",
            version="0.1.0",
        )

    def test_schemas_reject_terminal_result_without_a_typed_failure(self) -> None:
        invalid = {"status": "failed", "summary": "The agent failed."}
        with self.assertRaises(ValidationError):
            validate("run-result.schema.json", invalid)

    def test_schemas_reject_unknown_core_message_type(self) -> None:
        invalid = {
            "lap": "0.1",
            "id": "invalid-1",
            "producer": "agent.example",
            "seq": 1,
            "type": "run.hidden_reasoning",
            "payload": {},
        }
        with self.assertRaises(ValidationError):
            validate("envelope.schema.json", invalid)

    def test_context_schema_requires_a_digest_for_local_input_artifacts(self) -> None:
        invalid = {
            "artifacts": [{
                "id": "input-01",
                "name": "brief.txt",
                "media_type": "text/plain",
                "uri": "lap://run/input/001-input-01.txt",
            }]
        }
        with self.assertRaises(ValidationError):
            validate("context-packet.schema.json", invalid)

    def test_context_schema_rejects_an_unsafe_local_input_uri(self) -> None:
        invalid = {
            "artifacts": [{
                "id": "input-01",
                "name": "brief.txt",
                "media_type": "text/plain",
                "uri": "lap://run/input/../private.txt",
                "sha256": "3e3a7f18d29f5288be1f9238ce70c90e9af3cba55cf3cac2910eeec8a7528bb1",
            }]
        }
        with self.assertRaises(ValidationError):
            validate("context-packet.schema.json", invalid)

    def test_conformance_report_example_is_machine_readable(self) -> None:
        report = load_json(ROOT / "conformance" / "conformance-report.example.json")
        validate("conformance-report.schema.json", report)
        all_published_families = dict(report)
        all_published_families["profiles"] = [
            "lap-core/0.1",
            "lap-local/0.1",
            "lap-a2a-bridge/0.1",
            "lap-a2a-inline-inputs/0.1",
            "lap-package-signing/0.1",
            "lap-workflow/0.1",
            "lap-host-metering/0.1",
        ]
        all_published_families["results"] = [
            {"id": "SIGN-01", "status": "passed", "evidence": "signature test"},
            {"id": "INLINE-01", "status": "passed", "evidence": "inline vector"},
            {"id": "METER-01", "status": "passed", "evidence": "metering vector"},
            {"id": "FLOW-11", "status": "passed", "evidence": "workflow admission test"},
        ]
        validate("conformance-report.schema.json", all_published_families)
        invalid = dict(report)
        invalid["profiles"] = []
        with self.assertRaises(ValidationError):
            validate("conformance-report.schema.json", invalid)
        invalid_id = dict(report)
        invalid_id["results"] = [{"id": "UNKNOWN-01", "status": "passed", "evidence": "invalid"}]
        with self.assertRaises(ValidationError):
            validate("conformance-report.schema.json", invalid_id)


if __name__ == "__main__":
    unittest.main()
