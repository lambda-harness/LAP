"""Run one bounded LAP Local wire probe against an explicit Agent package.

This author-side tool executes the package entry point the author supplied in
``agent.json``. It validates one successful, declared capability invocation;
it does not install a package, grant authority, or certify a Host Runtime.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
MAX_FRAME_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4 * MAX_FRAME_BYTES
CHECKER = FormatChecker()


class ProbeError(RuntimeError):
    """Represent a stable, display-safe failure from the public Local probe.

    Args:
        code: Stable LAP error code.
        message: Safe explanation without raw command or package data.
    """

    def __init__(self, code: str, message: str) -> None:
        """Initialize the safe failure record.

        Args:
            code: Stable LAP error code.
            message: Safe explanation for an Agent author.
        """
        self.code = code
        self.message = message.strip() or "LAP Local probe failed."
        super().__init__(f"{self.code}: {self.message}")


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(
            "LAP-201", f"{label} could not be read as UTF-8 JSON."
        ) from exc


def _schema(name: str) -> dict[str, Any]:
    value = _load_json(ROOT / "schemas" / name, f"Schema {name}")
    if not isinstance(value, dict):
        raise ProbeError("LAP-500", f"Schema {name} is not an object.")
    return value


def _validate_schema(name: str, value: Any, label: str, *, code: str) -> None:
    try:
        Draft202012Validator(_schema(name), format_checker=CHECKER).validate(value)
    except SchemaError as exc:
        raise ProbeError("LAP-500", f"Schema {name} is invalid.") from exc
    except ValidationError as exc:
        raise ProbeError(code, f"{label} does not conform to {name}.") from exc


def _contract_schema(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProbeError("LAP-201", f"{label} must be a JSON Schema object.")

    def inspect(node: Any) -> None:
        if isinstance(node, dict):
            declared_draft = node.get("$schema")
            if (
                declared_draft is not None
                and declared_draft != "https://json-schema.org/draft/2020-12/schema"
            ):
                raise ProbeError(
                    "LAP-201", f"{label} declares an unsupported JSON Schema draft."
                )
            if "$id" in node:
                raise ProbeError("LAP-201", f"{label} must not declare $id.")
            for reference_key in ("$ref", "$dynamicRef", "$recursiveRef"):
                reference = node.get(reference_key)
                if reference is not None and (
                    not isinstance(reference, str) or not reference.startswith("#")
                ):
                    raise ProbeError(
                        "LAP-201",
                        f"{label} must use only local JSON Schema references.",
                    )
            for child in node.values():
                inspect(child)
        elif isinstance(node, list):
            for child in node:
                inspect(child)

    inspect(value)
    try:
        Draft202012Validator.check_schema(value)
    except SchemaError as exc:
        raise ProbeError(
            "LAP-201", f"{label} is not a valid JSON Schema Draft 2020-12 resource."
        ) from exc
    return value


def _validate_contract(
    schema: dict[str, Any], value: Any, label: str, *, code: str
) -> None:
    try:
        Draft202012Validator(schema, format_checker=CHECKER).validate(value)
    except ValidationError as exc:
        raise ProbeError(
            code, f"{label} does not satisfy its declared JSON Schema."
        ) from exc


def _package_directory(value: str) -> Path:
    package = Path(value)
    try:
        resolved = package.resolve(strict=True)
    except OSError as exc:
        raise ProbeError(
            "LAP-201", "Package directory does not exist or cannot be resolved."
        ) from exc
    if not resolved.is_dir():
        raise ProbeError(
            "LAP-201", "Package path must be a directory containing agent.json."
        )
    return resolved


def _package_relative(
    root: Path, value: Any, label: str, *, directory: bool = False
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProbeError(
            "LAP-201", f"{label} must be a non-empty package-relative path."
        )
    candidate = Path(value)
    if candidate.is_absolute():
        raise ProbeError("LAP-201", f"{label} must be package-relative.")
    try:
        resolved = (root / candidate).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ProbeError(
            "LAP-201", f"{label} escapes or is missing from the package."
        ) from exc
    if directory and not resolved.is_dir():
        raise ProbeError("LAP-201", f"{label} must name a package directory.")
    if not directory and not resolved.is_file():
        raise ProbeError("LAP-201", f"{label} must name a package file.")
    return resolved


def _manifest(package: Path) -> dict[str, Any]:
    value = _load_json(package / "agent.json", "agent.json")
    if not isinstance(value, dict):
        raise ProbeError("LAP-201", "agent.json must be an object.")
    _validate_schema("agent-manifest.schema.json", value, "agent.json", code="LAP-201")
    transport = value.get("transport")
    if not isinstance(transport, dict) or transport.get("kind") != "lap-local":
        raise ProbeError("LAP-204", "This probe supports only lap-local packages.")
    command = transport.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise ProbeError(
            "LAP-201",
            "agent.json transport.command must be a non-empty argument vector.",
        )
    _package_relative(
        package,
        transport.get("working_directory", "."),
        "transport.working_directory",
        directory=True,
    )
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ProbeError("LAP-201", "agent.json must declare at least one capability.")
    return value


def _select_capability(
    manifest: dict[str, Any], requested: str | None
) -> dict[str, Any]:
    capabilities = manifest["capabilities"]
    if requested is None:
        if len(capabilities) != 1:
            raise ProbeError(
                "LAP-201",
                "--capability is required when the package declares multiple capabilities.",
            )
        selected = capabilities[0]
    else:
        selected = next(
            (
                item
                for item in capabilities
                if isinstance(item, dict) and item.get("id") == requested
            ),
            None,
        )
        if selected is None:
            raise ProbeError(
                "LAP-404", "Requested capability is not declared by agent.json."
            )
    if not isinstance(selected, dict) or not isinstance(selected.get("id"), str):
        raise ProbeError("LAP-201", "agent.json capability is invalid.")
    return selected


def _probe_input(capability: dict[str, Any], raw_input: str | None) -> Any:
    if raw_input is None:
        value: Any = {"text": "LAP Local conformance probe"}
    else:
        try:
            value = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            raise ProbeError("LAP-201", "--input must be valid JSON.") from exc
    schema = _contract_schema(
        capability.get("input_schema", {}), "Capability input_schema"
    )
    _validate_contract(schema, value, "Probe input", code="LAP-201")
    return value


def _command(package: Path, manifest: dict[str, Any]) -> tuple[list[str], Path]:
    transport = manifest["transport"]
    command = list(transport["command"])
    working_directory = _package_relative(
        package,
        transport.get("working_directory", "."),
        "transport.working_directory",
        directory=True,
    )
    executable = command[0]
    if Path(executable).is_absolute():
        # Absolute host executables are valid LAP Local entries under a Host's
        # explicit allowlist. This author-side probe does not evaluate that policy.
        return command, working_directory
    if "/" in executable or "\\" in executable or executable.startswith("."):
        command[0] = str(_package_relative(package, executable, "transport.command[0]"))
    return command, working_directory


def _host_frames(capability_id: str, capability_input: Any) -> list[dict[str, Any]]:
    vector = _load_json(
        ROOT / "conformance" / "local-stdio-roundtrip.json", "Local round-trip vector"
    )
    if not isinstance(vector, dict) or not isinstance(vector.get("host_frames"), list):
        raise ProbeError("LAP-500", "Local round-trip vector is invalid.")
    frames = cast(list[dict[str, Any]], copy.deepcopy(vector["host_frames"]))
    if len(frames) != 3 or not all(isinstance(frame, dict) for frame in frames):
        raise ProbeError(
            "LAP-500", "Local round-trip vector has an invalid Host frame sequence."
        )
    frames[1]["payload"] = {"capability": capability_id, "input": capability_input}
    for frame in frames:
        _validate_schema(
            "envelope.schema.json", frame, "Host probe frame", code="LAP-500"
        )
    return frames


def _run(
    command: list[str],
    working_directory: Path,
    frames: list[dict[str, Any]],
    timeout_seconds: float,
) -> str:
    stdin = (
        "\n".join(
            json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
            for frame in frames
        )
        + "\n"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=working_directory,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProbeError(
            "LAP-201", "The declared Local Agent executable could not be started."
        ) from exc
    except OSError as exc:
        raise ProbeError(
            "LAP-500", "The declared Local Agent process could not be started."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(
            "LAP-401", "The Local Agent did not complete the probe before its timeout."
        ) from exc
    if completed.returncode != 0:
        raise ProbeError(
            "LAP-500",
            f"The Local Agent exited with code {completed.returncode} before successful completion.",
        )
    if len(completed.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ProbeError(
            "LAP-101", "The Local Agent stdout exceeds the probe output limit."
        )
    return completed.stdout


def _agent_frames(stdout: str) -> list[dict[str, Any]]:
    if not stdout:
        raise ProbeError("LAP-101", "The Local Agent produced no LAP stdout frames.")
    frames: list[dict[str, Any]] = []
    for raw in stdout.splitlines():
        if not raw.strip():
            raise ProbeError(
                "LAP-101", "The Local Agent stdout contains a non-protocol blank line."
            )
        if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
            raise ProbeError(
                "LAP-101", "The Local Agent emitted an oversized stdout frame."
            )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProbeError(
                "LAP-101", "The Local Agent stdout contains non-JSON protocol data."
            ) from exc
        if not isinstance(value, dict):
            raise ProbeError(
                "LAP-101", "The Local Agent stdout frame must be an object."
            )
        _validate_schema(
            "envelope.schema.json", value, "Agent stdout frame", code="LAP-101"
        )
        frames.append(value)
    return frames


def _verify_exchange(
    manifest: dict[str, Any],
    capability: dict[str, Any],
    host_frames: list[dict[str, Any]],
    agent_frames: list[dict[str, Any]],
) -> dict[str, Any]:
    agent_id = manifest.get("id")
    version = manifest.get("version")
    if not isinstance(agent_id, str) or not isinstance(version, str):
        raise ProbeError(
            "LAP-201", "agent.json must declare Agent identity and version."
        )
    if len(agent_frames) < 3:
        raise ProbeError(
            "LAP-101",
            "The Local Agent did not complete the required handshake and terminal lifecycle.",
        )
    types = [frame.get("type") for frame in agent_frames]
    if (
        types[0] != "agent.welcome"
        or types[1] != "run.accepted"
        or types[-1] != "run.result"
    ):
        raise ProbeError(
            "LAP-101", "The Local Agent emitted an invalid LAP Local lifecycle order."
        )
    if any(item not in {"run.progress", "run.artifact"} for item in types[2:-1]):
        raise ProbeError(
            "LAP-101",
            "The Local Agent emitted an unsupported non-terminal probe frame.",
        )
    if (
        types.count("agent.welcome") != 1
        or types.count("run.accepted") != 1
        or types.count("run.result") != 1
    ):
        raise ProbeError(
            "LAP-101", "The Local Agent emitted a duplicate lifecycle transition."
        )
    raw_sequences = [frame.get("seq") for frame in agent_frames]
    if not all(isinstance(item, int) and item > 0 for item in raw_sequences):
        raise ProbeError(
            "LAP-101", "The Local Agent sequence values are not strictly increasing."
        )
    sequences = [cast(int, item) for item in raw_sequences]
    if any(current <= previous for previous, current in zip(sequences, sequences[1:])):
        raise ProbeError(
            "LAP-101", "The Local Agent sequence values are not strictly increasing."
        )
    if len({frame.get("id") for frame in agent_frames}) != len(agent_frames):
        raise ProbeError(
            "LAP-101", "The Local Agent emitted duplicate message identifiers."
        )
    if any(frame.get("producer") != agent_id for frame in agent_frames):
        raise ProbeError(
            "LAP-103", "The Local Agent producer does not match agent.json identity."
        )

    welcome = agent_frames[0]
    welcome_payload = welcome.get("payload")
    if (
        welcome.get("correlation_id") != host_frames[0]["id"]
        or not isinstance(welcome_payload, dict)
        or welcome_payload.get("selected_lap") != "0.1"
        or welcome_payload.get("agent_id") != agent_id
        or welcome_payload.get("version") != version
        or "lap-local/0.1" not in welcome_payload.get("profiles", [])
    ):
        raise ProbeError(
            "LAP-103",
            "The Local Agent welcome does not prove the declared Local identity.",
        )

    run = host_frames[1]["run"]
    accepted = agent_frames[1]
    if (
        accepted.get("correlation_id") != host_frames[1]["id"]
        or accepted.get("run") != run
    ):
        raise ProbeError("LAP-103", "The Local Agent accepted an unrelated run.")
    if any(frame.get("run") != run for frame in agent_frames[1:]):
        raise ProbeError(
            "LAP-103", "The Local Agent emitted a run-scoped frame for another run."
        )

    terminal = agent_frames[-1]
    payload = terminal.get("payload")
    _validate_schema(
        "run-result.schema.json", payload, "Terminal run.result payload", code="LAP-101"
    )
    if not isinstance(payload, dict) or payload.get("status") != "succeeded":
        raise ProbeError(
            "LAP-500",
            "The Local Agent did not return a successful terminal result for the probe.",
        )
    if "output" not in payload:
        raise ProbeError(
            "LAP-101", "A successful Local Agent result must include output."
        )
    output_schema = _contract_schema(
        capability.get("output_schema", {}), "Capability output_schema"
    )
    _validate_contract(
        output_schema, payload["output"], "Successful terminal output", code="LAP-101"
    )
    return {
        "valid": True,
        "suite": "lap-local-probe/0.1",
        "profile": "lap-local/0.1",
        "agent": {
            "id": agent_id,
            "version": version,
            "capability": capability["id"],
        },
        "frames": {"count": len(agent_frames), "types": types},
        "terminal": {"status": "succeeded", "output_contract": "validated"},
    }


def run_probe(
    package_path: str,
    *,
    capability_id: str | None,
    input_json: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run one bounded Local Profile exchange against a package entry point.

    Args:
        package_path: Directory containing the Agent package ``agent.json``.
        capability_id: Optional selected capability for a multi-capability Agent.
        input_json: Optional JSON string for the selected capability input.
        timeout_seconds: End-to-end subprocess timeout between 0.1 and 300.

    Returns:
        Safe, machine-readable validation report for a successful exchange.

    Raises:
        ProbeError: If preflight, transport, lifecycle, or contract validation
            fails.
    """
    if not 0.1 <= timeout_seconds <= 300:
        raise ProbeError("LAP-201", "--timeout-seconds must be between 0.1 and 300.")
    package = _package_directory(package_path)
    manifest = _manifest(package)
    capability = _select_capability(manifest, capability_id)
    capability_input = _probe_input(capability, input_json)
    command, working_directory = _command(package, manifest)
    host_frames = _host_frames(capability["id"], capability_input)
    agent_frames = _agent_frames(
        _run(command, working_directory, host_frames, timeout_seconds)
    )
    return _verify_exchange(manifest, capability, host_frames, agent_frames)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments for the public Local Profile probe command.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run one bounded LAP Local wire probe for the package entry point declared in agent.json."
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
    """Execute the Local Profile probe and emit a safe JSON result.

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
    except (
        Exception
    ) as exc:  # Keep accidental implementation failures safe for CI logs.
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": {
                        "code": "LAP-500",
                        "message": f"LAP Local probe failed: {type(exc).__name__}.",
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
