"""Minimal LAP Local orchestrator; stdout contains protocol frames only."""

from __future__ import annotations

import json
import sys
from typing import Any

AGENT_ID = "org.lap.orchestrator-agent"
EXTENSION_KEY = "io.github.lambda-harness.lap.workflow.orchestrator"
sequence = 0


def emit(
    message_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: str | None = None,
    run: dict[str, Any] | None = None,
) -> None:
    """Emit one ordered LAP protocol frame to standard output.

    Args:
        message_type: LAP message type to emit.
        payload: Protocol payload associated with the message.
        correlation_id: Optional Host message identifier being answered.
        run: Optional Host-owned run identity to preserve in the frame.
    """
    global sequence
    sequence += 1
    frame: dict[str, Any] = {
        "lap": "0.1",
        "id": f"orchestrator-{sequence}",
        "producer": AGENT_ID,
        "seq": sequence,
        "type": message_type,
        "payload": payload,
    }
    if correlation_id:
        frame["correlation_id"] = correlation_id
    if run:
        frame["run"] = run
    print(json.dumps(frame, ensure_ascii=False, separators=(",", ":")), flush=True)


def dispatch_from_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Build one proposal from the Host-scoped workflow context.

    Args:
        payload: ``run.start`` payload containing the workflow extension.

    Returns:
        A dispatch proposal limited to the first Host-granted target.

    Raises:
        ValueError: If the required Host workflow extension is invalid.
    """
    context = payload.get("context")
    extensions = context.get("extensions") if isinstance(context, dict) else None
    extension = extensions.get(EXTENSION_KEY) if isinstance(extensions, dict) else None
    if not isinstance(extension, dict) or extension.get("version") != "0.2":
        raise ValueError("Missing LAP workflow orchestrator context.")
    allowed = extension.get("allowed_dispatches")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("Workflow orchestrator context has no dispatch targets.")
    target = allowed[0]
    if not isinstance(target, dict):
        raise ValueError(
            "Workflow orchestrator context has an invalid dispatch target."
        )
    agent_id = target.get("agent_id")
    capabilities = target.get("capabilities")
    if (
        not isinstance(agent_id, str)
        or not isinstance(capabilities, list)
        or not capabilities
    ):
        raise ValueError(
            "Workflow orchestrator context has an invalid dispatch target."
        )
    capability = capabilities[0]
    if not isinstance(capability, str):
        raise ValueError("Workflow orchestrator context has an invalid capability.")
    return {
        "dispatch": [
            {
                "agent_id": agent_id,
                "capability": capability,
                "input": payload.get("input"),
            }
        ],
    }


def handle(frame: dict[str, Any]) -> bool:
    """Handle one Host frame and report whether the Agent should keep running.

    Args:
        frame: Parsed LAP envelope supplied by the Host.

    Returns:
        ``False`` after a shutdown request; otherwise ``True``.
    """
    message_type = frame.get("type")
    if message_type == "agent.hello":
        emit(
            "agent.welcome",
            {
                "selected_lap": "0.1",
                "profiles": ["lap-local/0.1", "lap-workflow/0.2"],
                "agent_id": AGENT_ID,
                "version": "0.1.0",
                "max_concurrency": 1,
            },
            correlation_id=str(frame.get("id") or ""),
        )
        return True
    if message_type == "run.start":
        run = frame.get("run") or {}
        payload = frame.get("payload") or {}
        emit(
            "run.accepted",
            {"capability": payload.get("capability")},
            correlation_id=str(frame.get("id") or ""),
            run=run,
        )
        try:
            output = dispatch_from_context(payload)
        except ValueError as exc:
            emit(
                "run.result",
                {
                    "status": "failed",
                    "summary": "Workflow context was rejected.",
                    "error": {
                        "code": "LAP-201",
                        "message": str(exc),
                        "retryable": False,
                    },
                },
                run=run,
            )
            return True
        emit(
            "run.progress",
            {
                "phase": "planning",
                "message": "Constructed a proposal from the Host-scoped dispatch context.",
            },
            run=run,
        )
        emit(
            "run.result",
            {
                "status": "succeeded",
                "summary": "Proposed one Host-constrained dispatch.",
                "output": output,
            },
            run=run,
        )
        return True
    if message_type == "run.cancel":
        emit(
            "run.result",
            {
                "status": "cancelled",
                "summary": "Run cancelled.",
                "error": {
                    "code": "LAP-401",
                    "message": "Cancellation requested.",
                    "retryable": False,
                },
            },
            run=frame.get("run") or {},
        )
        return True
    if message_type == "agent.shutdown":
        return False
    return True


for raw in sys.stdin:
    try:
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise ValueError("frame must be an object")
    except (json.JSONDecodeError, ValueError):
        sys.exit(2)
    if not handle(message):
        break
