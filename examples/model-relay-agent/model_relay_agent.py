"""Draft LAP Model Relay reference Agent.

The process has no provider URL, API key, or direct model client.  It proves
only the proposed Local stdio exchange used by tools/lap_model_relay_probe.py.
"""

from __future__ import annotations

import json
import sys
from typing import Any, cast

AGENT_ID = "org.lap.model-relay-agent"
VERSION = "0.1.0"
RELAY_PROFILE = "lap-model-relay/0.1"
RELAY_EXTENSION = "io.github.lambda-harness.lap.model-relay"
sequence = 0
pending_request_id: str | None = None
active_run: dict[str, str] | None = None


def _object_map(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, Any], value)


def _string_map(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        return None
    return cast(dict[str, str], value)


def emit(
    message_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: str | None = None,
    run: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Emit one ordered draft Model Relay protocol frame.

    Args:
        message_type: Draft LAP message type to emit.
        payload: Protocol payload associated with the message.
        correlation_id: Optional Host message identifier being answered.
        run: Optional Host-owned run identity to preserve in the frame.
        idempotency_key: Optional key bound to the relay request lifecycle.

    Returns:
        Identifier assigned to the emitted Agent frame.
    """
    global sequence
    sequence += 1
    message_id = f"relay-agent-{sequence}"
    frame: dict[str, Any] = {
        "lap": "0.1",
        "id": message_id,
        "producer": AGENT_ID,
        "seq": sequence,
        "type": message_type,
        "payload": payload,
    }
    if correlation_id:
        frame["correlation_id"] = correlation_id
    if run:
        frame["run"] = run
    if idempotency_key:
        frame["idempotency_key"] = idempotency_key
    print(json.dumps(frame, ensure_ascii=False, separators=(",", ":")), flush=True)
    return message_id


def fail_run(code: str, message: str) -> None:
    """Emit a typed failed terminal result for the currently active relay run.

    Args:
        code: Stable LAP error code.
        message: Safe explanation of the relay failure.
    """
    if active_run is None:
        return
    emit(
        "run.result",
        {
            "status": "failed",
            "summary": "Host relay exchange failed.",
            "error": {"code": code, "message": message},
        },
        run=active_run,
    )


for raw in sys.stdin:
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError:
        continue
    if not isinstance(frame, dict):
        continue
    message_type = frame.get("type")
    payload = _object_map(frame.get("payload"))

    if message_type == "agent.hello":
        offered = payload.get("profiles")
        if (
            not isinstance(offered, list)
            or "lap-local/0.1" not in offered
            or RELAY_PROFILE not in offered
        ):
            continue
        emit(
            "agent.welcome",
            {
                "selected_lap": "0.1",
                "profiles": ["lap-local/0.1", RELAY_PROFILE],
                "agent_id": AGENT_ID,
                "version": VERSION,
                "max_concurrency": 1,
            },
            correlation_id=str(frame.get("id") or ""),
        )
    elif message_type == "run.start":
        run = _string_map(frame.get("run"))
        context = _object_map(payload.get("context"))
        extensions = _object_map(context.get("extensions"))
        relay = extensions.get(RELAY_EXTENSION)
        if not isinstance(run, dict) or not isinstance(relay, dict):
            active_run = run if isinstance(run, dict) else None
            fail_run("LAP-204", "The Host did not grant the Model Relay Profile.")
            continue
        routes = relay.get("routes")
        if relay.get("version") != "0.1" or not isinstance(routes, list) or not routes:
            active_run = run
            fail_run("LAP-201", "The Host relay context is invalid.")
            continue
        first_route = routes[0]
        if not isinstance(first_route, dict) or not isinstance(
            first_route.get("id"), str
        ):
            active_run = run
            fail_run("LAP-201", "The Host relay route is invalid.")
            continue
        active_run = run
        input_value = _object_map(payload.get("input"))
        text = input_value.get("text")
        if not isinstance(text, str) or not text:
            fail_run("LAP-201", "The capability input is invalid.")
            continue
        emit(
            "run.accepted",
            {"capability": payload.get("capability")},
            correlation_id=str(frame.get("id") or ""),
            run=active_run,
        )
        emit(
            "run.progress",
            {
                "phase": "model.relay_request",
                "message": "Requesting the Host model relay.",
            },
            run=active_run,
        )
        pending_request_id = emit(
            "model.request",
            {
                "route": first_route["id"],
                "input": {"messages": [{"role": "user", "content": text}]},
                "max_output_tokens": min(
                    128, int(first_route.get("max_output_tokens") or 128)
                ),
            },
            run=active_run,
            idempotency_key=f"relay-{active_run.get('run_id', 'run')}-1",
        )
    elif message_type == "model.response":
        if active_run is None or pending_request_id is None:
            continue
        if (
            frame.get("correlation_id") != pending_request_id
            or frame.get("run") != active_run
        ):
            fail_run("LAP-103", "The Host relay response is not bound to this request.")
            continue
        if payload.get("status") != "succeeded":
            error = _object_map(payload.get("error"))
            fail_run(
                str(error.get("code") or "LAP-500"),
                str(error.get("message") or "Host relay failed."),
            )
            continue
        output = _object_map(payload.get("output"))
        text = output.get("text")
        if not isinstance(text, str) or not text:
            fail_run("LAP-101", "The Host relay response has no text output.")
            continue
        emit(
            "run.progress",
            {
                "phase": "model.relay_response",
                "message": "Received the Host model relay response.",
            },
            run=active_run,
        )
        emit(
            "run.result",
            {
                "status": "succeeded",
                "summary": "Host relay response completed.",
                "output": {"model_text": text},
            },
            run=active_run,
        )
        pending_request_id = None
    elif message_type == "run.cancel":
        if active_run is not None:
            emit(
                "run.result",
                {
                    "status": "cancelled",
                    "summary": "Host cancelled the relay run.",
                    "error": {
                        "code": "LAP-401",
                        "message": "Host cancellation requested.",
                    },
                },
                run=active_run,
            )
            pending_request_id = None
    elif message_type == "agent.shutdown":
        break
