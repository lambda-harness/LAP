"""Exercise one draft LAP Model Relay exchange against a Local Agent package.

This author-side probe uses a deterministic Host response. It proves the
proposed stdio lifecycle only; it does not contact a model provider, install a
package, grant a production capability, or certify isolation or billing.
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

from lap_local_probe import (
    MAX_FRAME_BYTES,
    MAX_OUTPUT_BYTES,
    ProbeError,
    _command,
    _contract_schema,
    _manifest,
    _package_directory,
    _probe_input,
    _select_capability,
    _validate_contract,
    _validate_schema,
)

RELAY_PROFILE = "lap-model-relay/0.1"
RELAY_EXTENSION = "io.github.lambda-harness.lap.model-relay"
HOST_PRODUCER = "io.lambda-harness.model-relay-probe"
_ENVELOPE_FIELDS = frozenset(
    (
        "lap",
        "id",
        "correlation_id",
        "producer",
        "seq",
        "type",
        "run",
        "idempotency_key",
        "payload",
        "extensions",
    )
)
_RUN_FIELDS = frozenset(
    ("tenant_id", "session_id", "run_id", "parent_run_id", "trace_id")
)


def _host_frame(
    message_id: str,
    sequence: int,
    message_type: str,
    payload: dict[str, Any],
    *,
    run: dict[str, str] | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "lap": "0.1",
        "id": message_id,
        "producer": HOST_PRODUCER,
        "seq": sequence,
        "type": message_type,
        "payload": payload,
    }
    if run is not None:
        frame["run"] = run
    if correlation_id is not None:
        frame["correlation_id"] = correlation_id
    if idempotency_key is not None:
        frame["idempotency_key"] = idempotency_key
    return frame


def _validate_draft_envelope(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - _ENVELOPE_FIELDS:
        raise ProbeError("LAP-101", f"{label} is not a valid draft relay envelope.")
    required = {"lap", "id", "producer", "seq", "type", "payload"}
    if not required.issubset(value) or value.get("lap") != "0.1":
        raise ProbeError("LAP-101", f"{label} is missing required envelope fields.")
    for field in ("id", "producer"):
        item = value.get(field)
        if not isinstance(item, str) or not item or len(item) > 240:
            raise ProbeError("LAP-101", f"{label} has an invalid {field}.")
    if (
        not isinstance(value.get("seq"), int)
        or isinstance(value["seq"], bool)
        or value["seq"] < 0
    ):
        raise ProbeError("LAP-101", f"{label} has an invalid sequence.")
    if not isinstance(value.get("type"), str) or not value["type"]:
        raise ProbeError("LAP-101", f"{label} has an invalid type.")
    if not isinstance(value.get("payload"), dict):
        raise ProbeError("LAP-101", f"{label} payload must be an object.")
    for field in ("correlation_id", "idempotency_key"):
        if field in value and (
            not isinstance(value[field], str)
            or not value[field]
            or len(value[field]) > 240
        ):
            raise ProbeError("LAP-101", f"{label} has an invalid {field}.")
    if "run" in value:
        run = value["run"]
        if not isinstance(run, dict) or set(run) - _RUN_FIELDS:
            raise ProbeError("LAP-101", f"{label} has an invalid run identity.")
        required_run = {"tenant_id", "session_id", "run_id", "trace_id"}
        if not required_run.issubset(run) or any(
            not isinstance(run.get(field), str)
            or not run[field]
            or len(run[field]) > 240
            for field in required_run
        ):
            raise ProbeError("LAP-101", f"{label} has an invalid run identity.")
    return value


class _LocalExchange:
    """One bounded interactive stdio exchange with no shell invocation."""

    def __init__(
        self, command: list[str], working_directory: Path, timeout_seconds: float
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.deadline = time.monotonic() + timeout_seconds
        self._output_bytes = 0
        self._lines: queue.Queue[str | None] = queue.Queue()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise ProbeError(
                "LAP-201", "The declared Local Agent executable could not be started."
            ) from exc
        except OSError as exc:
            raise ProbeError(
                "LAP-500", "The declared Local Agent process could not be started."
            ) from exc
        self._reader = threading.Thread(target=self._drain_stdout, daemon=True)
        self._reader.start()

    def _drain_stdout(self) -> None:
        if self.process.stdout is not None:
            for line in self.process.stdout:
                self._lines.put(line)
        self._lines.put(None)

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError(
                "LAP-401",
                "The Local Agent did not complete the relay probe before its timeout.",
            )
        return remaining

    def send(self, frame: dict[str, Any]) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            raise ProbeError(
                "LAP-500", "The Local Agent exited before receiving a Host frame."
            )
        encoded = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_FRAME_BYTES:
            raise ProbeError(
                "LAP-500", "The draft probe generated an oversized Host frame."
            )
        try:
            self.process.stdin.write(encoded + "\n")
            self.process.stdin.flush()
        except OSError as exc:
            raise ProbeError(
                "LAP-500", "The Local Agent stdin is unavailable."
            ) from exc

    def receive(self) -> dict[str, Any]:
        try:
            raw = self._lines.get(timeout=self._remaining())
        except queue.Empty as exc:
            raise ProbeError(
                "LAP-401",
                "The Local Agent did not emit a relay frame before its timeout.",
            ) from exc
        if raw is None:
            raise ProbeError(
                "LAP-500",
                "The Local Agent exited before completing the relay lifecycle.",
            )
        if not raw.strip():
            raise ProbeError(
                "LAP-101", "The Local Agent stdout contains a non-protocol blank line."
            )
        size = len(raw.encode("utf-8"))
        if size > MAX_FRAME_BYTES:
            raise ProbeError(
                "LAP-101", "The Local Agent emitted an oversized stdout frame."
            )
        self._output_bytes += size
        if self._output_bytes > MAX_OUTPUT_BYTES:
            raise ProbeError(
                "LAP-101",
                "The Local Agent stdout exceeds the relay probe output limit.",
            )
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProbeError(
                "LAP-101", "The Local Agent stdout contains non-JSON protocol data."
            ) from exc
        return _validate_draft_envelope(frame, "Agent relay frame")

    def close(self, *, expect_success: bool = False) -> None:
        if self.process.poll() is None and self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=min(2.0, max(0.1, self._remaining())))
        except (subprocess.TimeoutExpired, ProbeError):
            self.process.kill()
            self.process.wait(timeout=2)
        if expect_success and self.process.returncode != 0:
            raise ProbeError(
                "LAP-500",
                f"The Local Agent exited with code {self.process.returncode} after the relay lifecycle.",
            )


def _require_agent_frame(
    frame: dict[str, Any],
    expected_type: str,
    *,
    agent_id: str,
    run: dict[str, str] | None = None,
) -> None:
    if frame.get("type") != expected_type or frame.get("producer") != agent_id:
        raise ProbeError("LAP-101", f"Expected Agent {expected_type} frame.")
    if run is not None and frame.get("run") != run:
        raise ProbeError("LAP-103", "The Agent relay frame is bound to another run.")


def _probe_frames(
    manifest: dict[str, Any],
    capability: dict[str, Any],
    probe_input: Any,
    exchange: _LocalExchange,
) -> dict[str, Any]:
    agent_id = str(manifest["id"])
    version = str(manifest["version"])
    run = {
        "tenant_id": "tenant_probe",
        "session_id": "session_probe",
        "run_id": "run_model_relay_probe",
        "trace_id": "trace_model_relay_probe",
    }
    relay_context: dict[str, Any] = {
        "version": "0.1",
        "routes": [{"id": "host.default", "max_requests": 1, "max_output_tokens": 256}],
    }
    _validate_schema(
        "model-relay-context.schema.json",
        relay_context,
        "Relay context",
        code="LAP-500",
    )
    hello = _host_frame(
        "host-hello",
        1,
        "agent.hello",
        {
            "supported_lap": ["0.1"],
            "profiles": ["lap-local/0.1", RELAY_PROFILE],
            "host": HOST_PRODUCER,
        },
    )
    exchange.send(hello)
    welcome = exchange.receive()
    _require_agent_frame(welcome, "agent.welcome", agent_id=agent_id)
    welcome_payload = welcome["payload"]
    if (
        welcome.get("correlation_id") != hello["id"]
        or welcome_payload.get("selected_lap") != "0.1"
        or welcome_payload.get("agent_id") != agent_id
        or welcome_payload.get("version") != version
        or not isinstance(welcome_payload.get("profiles"), list)
        or "lap-local/0.1" not in welcome_payload["profiles"]
        or RELAY_PROFILE not in welcome_payload["profiles"]
    ):
        raise ProbeError(
            "LAP-204",
            "The Local Agent did not negotiate the draft Model Relay Profile.",
        )

    start = _host_frame(
        "host-run-start",
        2,
        "run.start",
        {
            "capability": capability["id"],
            "input": probe_input,
            "context": {
                "input": probe_input,
                "extensions": {RELAY_EXTENSION: relay_context},
            },
        },
        run=run,
        idempotency_key="relay-probe-run-1",
    )
    exchange.send(start)
    agent_frames: list[dict[str, Any]] = [welcome]
    accepted = exchange.receive()
    agent_frames.append(accepted)
    _require_agent_frame(accepted, "run.accepted", agent_id=agent_id, run=run)
    if accepted.get("correlation_id") != start["id"]:
        raise ProbeError("LAP-103", "The Agent accepted an unrelated relay run.")

    request: dict[str, Any] | None = None
    while request is None:
        frame = exchange.receive()
        agent_frames.append(frame)
        if frame.get("type") == "run.progress":
            _require_agent_frame(frame, "run.progress", agent_id=agent_id, run=run)
            continue
        _require_agent_frame(frame, "model.request", agent_id=agent_id, run=run)
        request = frame
    if not request.get("idempotency_key"):
        raise ProbeError("LAP-201", "The Agent relay request has no idempotency key.")
    _validate_schema(
        "model-relay-request.schema.json",
        request["payload"],
        "Relay request",
        code="LAP-101",
    )
    request_payload = request["payload"]
    route = cast(dict[str, Any], relay_context["routes"][0])
    if (
        request_payload["route"] != route["id"]
        or request_payload["max_output_tokens"] > route["max_output_tokens"]
    ):
        raise ProbeError(
            "LAP-401", "The Agent relay request exceeds its Host-granted route."
        )

    response_payload = {
        "status": "succeeded",
        "request_sha256": "d0b8b656f17d8a17789f78bd0c0b59251c43591fa330e17a73e36da5ca0892ce",
        "output": {"text": "Relay probe response."},
        "usage": {
            "source": "provider",
            "input_tokens": 16,
            "cached_tokens": 0,
            "output_tokens": 4,
        },
    }
    _validate_schema(
        "model-relay-response.schema.json",
        response_payload,
        "Relay response",
        code="LAP-500",
    )
    exchange.send(
        _host_frame(
            "host-model-response",
            3,
            "model.response",
            response_payload,
            run=run,
            correlation_id=request["id"],
            idempotency_key=str(request["idempotency_key"]),
        )
    )

    terminal: dict[str, Any] | None = None
    while terminal is None:
        frame = exchange.receive()
        agent_frames.append(frame)
        if frame.get("type") == "run.progress":
            _require_agent_frame(frame, "run.progress", agent_id=agent_id, run=run)
            continue
        _require_agent_frame(frame, "run.result", agent_id=agent_id, run=run)
        terminal = frame
    _validate_schema(
        "run-result.schema.json",
        terminal["payload"],
        "Relay terminal payload",
        code="LAP-101",
    )
    if terminal["payload"].get("status") != "succeeded":
        raise ProbeError(
            "LAP-500", "The Local Agent did not complete the relay probe successfully."
        )
    output = terminal["payload"].get("output")
    output_schema = _contract_schema(
        capability.get("output_schema", {}), "Capability output_schema"
    )
    _validate_contract(output_schema, output, "Relay terminal output", code="LAP-101")

    exchange.send(_host_frame("host-shutdown", 4, "agent.shutdown", {}))
    types = [str(frame["type"]) for frame in agent_frames]
    sequences = [int(frame["seq"]) for frame in agent_frames]
    if any(current <= previous for previous, current in zip(sequences, sequences[1:])):
        raise ProbeError(
            "LAP-101",
            "The Local Agent relay sequence values are not strictly increasing.",
        )
    if len({frame["id"] for frame in agent_frames}) != len(agent_frames):
        raise ProbeError(
            "LAP-101", "The Local Agent emitted duplicate relay message identifiers."
        )
    return {
        "valid": True,
        "suite": "lap-model-relay-probe/0.1-draft",
        "profile": RELAY_PROFILE,
        "agent": {"id": agent_id, "version": version, "capability": capability["id"]},
        "frames": {"count": len(agent_frames), "types": types},
        "relay": {
            "route": route["id"],
            "response": "deterministic-host-simulation",
            "provider_calls": 0,
        },
        "terminal": {"status": "succeeded", "output_contract": "validated"},
    }


def run_probe(
    package_path: str,
    *,
    capability_id: str | None,
    input_json: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run the deterministic draft Model Relay exchange for one Local package.

    Args:
        package_path: Directory containing the Agent package ``agent.json``.
        capability_id: Optional selected capability for a multi-capability Agent.
        input_json: Optional JSON string for the selected capability input.
        timeout_seconds: End-to-end subprocess timeout between 0.1 and 300.

    Returns:
        Safe, machine-readable report for a successful relay exchange.

    Raises:
        ProbeError: If the package does not negotiate or complete the draft
            Model Relay exchange.
    """
    if not 0.1 <= timeout_seconds <= 300:
        raise ProbeError("LAP-201", "--timeout-seconds must be between 0.1 and 300.")
    package = _package_directory(package_path)
    manifest = _manifest(package)
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list) or RELAY_PROFILE not in profiles:
        raise ProbeError(
            "LAP-204", "agent.json does not declare the draft Model Relay Profile."
        )
    capability = _select_capability(manifest, capability_id)
    probe_input = _probe_input(capability, input_json)
    command, working_directory = _command(package, manifest)
    exchange = _LocalExchange(command, working_directory, timeout_seconds)
    try:
        result = _probe_frames(manifest, capability, probe_input, exchange)
    except BaseException:
        exchange.close()
        raise
    exchange.close(expect_success=True)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments for the draft Model Relay probe command.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run one deterministic draft LAP Model Relay exchange against a Local Agent package."
    )
    parser.add_argument(
        "--package", required=True, help="directory containing agent.json"
    )
    parser.add_argument(
        "--capability",
        help="declared capability to invoke; required for multi-capability packages",
    )
    parser.add_argument(
        "--input",
        dest="input_json",
        help="JSON capability input; defaults to a text probe when valid",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="bounded process timeout (default: 30)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Execute the draft Model Relay probe and emit a safe JSON result.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Zero for a valid exchange and two for a typed validation failure.
    """
    args = parse_args(argv)
    try:
        report = run_probe(
            args.package,
            capability_id=args.capability,
            input_json=args.input_json,
            timeout_seconds=args.timeout_seconds,
        )
    except ProbeError as exc:
        print(
            json.dumps(
                {"valid": False, "error": {"code": exc.code, "message": exc.message}},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": {
                        "code": "LAP-500",
                        "message": f"LAP Model Relay probe failed: {type(exc).__name__}.",
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
