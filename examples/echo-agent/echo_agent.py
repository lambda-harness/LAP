"""Minimal LAP Local 0.1 reference agent; stdout contains protocol frames only."""
from __future__ import annotations

import json
import sys
from typing import Any


sequence = 0


def emit(message_type: str, payload: dict[str, Any], *, correlation_id: str | None = None,
         run: dict[str, Any] | None = None) -> None:
    global sequence
    sequence += 1
    frame: dict[str, Any] = {
        "lap": "0.1",
        "id": f"echo-{sequence}",
        "producer": "org.lap.echo-agent",
        "seq": sequence,
        "type": message_type,
        "payload": payload,
    }
    if correlation_id:
        frame["correlation_id"] = correlation_id
    if run:
        frame["run"] = run
    print(json.dumps(frame, ensure_ascii=False, separators=(",", ":")), flush=True)


def handle(frame: dict[str, Any]) -> bool:
    message_type = frame.get("type")
    if message_type == "agent.hello":
        emit("agent.welcome", {
            "selected_lap": "0.1",
            "profiles": ["lap-local/0.1"],
            "agent_id": "org.lap.echo-agent",
            "version": "0.1.0",
            "max_concurrency": 1,
        }, correlation_id=str(frame.get("id") or ""))
        return True
    if message_type == "run.start":
        run = frame.get("run") or {}
        emit("run.accepted", {"capability": frame.get("payload", {}).get("capability")},
             correlation_id=str(frame.get("id") or ""), run=run)
        emit("run.progress", {"phase": "agent", "message": "Echoing input."}, run=run)
        text = str((frame.get("payload", {}).get("input") or {}).get("text") or "")
        emit("run.result", {"status": "succeeded", "summary": "Echo complete.",
             "output": {"text": text}}, run=run)
        return True
    if message_type == "run.cancel":
        emit("run.result", {"status": "cancelled", "summary": "Run cancelled.",
             "error": {"code": "LAP-401", "message": "Cancellation requested.",
                       "retryable": False}}, run=frame.get("run") or {})
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
        # A production Host terminates malformed peers; this example exits cleanly.
        sys.exit(2)
    if not handle(message):
        break
