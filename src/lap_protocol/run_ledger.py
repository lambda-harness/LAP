"""Reference Core 0.2 Run terminal and structured-error semantics.

The ledger makes the Host-owned state machine executable in one process. It
does not replace a durable database, distributed transaction, effect provider
reconciliation, peer authentication, or an audit sink. A production Host must
persist its transition, Artifact receipt gate, terminal record, and outbound
acknowledgement atomically before it acknowledges a terminal result.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, cast

from .artifact_ledger import ArtifactLedger, ArtifactScope
from .effect_ledger import EffectLedger

_TERMINAL_STATES: Final = frozenset(
    ("succeeded", "failed", "cancelled", "timed_out", "indeterminate")
)
_ACTIVE_STATES: Final = frozenset(
    ("starting", "running", "input_required", "approval_required", "reconciling")
)
_RESULT_STATES: Final = _TERMINAL_STATES
_RESPONSIBILITIES: Final = frozenset(("host", "agent", "transport", "profile"))
_ERROR_CODE_RE: Final = re.compile(r"^LAP-[1-5][0-9]{2}$")
_FINGERPRINT_DOMAIN: Final = b"LAP-CORE-0.2-RUN-EVENT\n"


class RunLedgerError(ValueError):
    """Represent one safe, typed Run-lifecycle rejection."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the rejection with its stable LAP code and safe message."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class RunValidationError(RunLedgerError):
    """Reject malformed Run payloads, scope, identifiers, or error metadata."""

    def __init__(self, message: str) -> None:
        """Initialize a Core input-validation rejection."""
        super().__init__("LAP-201", message)


class RunStateError(RunLedgerError):
    """Reject an event that is not legal from the authoritative Run state."""

    def __init__(self, message: str) -> None:
        """Initialize a Core lifecycle-state rejection."""
        super().__init__("LAP-201", message)


class RunConflictError(RunLedgerError):
    """Reject reused event identities or later terminal proposals that differ."""

    def __init__(self, message: str) -> None:
        """Initialize the immutable-record conflict rejection."""
        super().__init__("LAP-109", message)


class RunTerminalConflictError(RunConflictError):
    """Reject an event that tries to change an already terminal Run."""


@dataclass(frozen=True)
class SafeError:
    """Immutable, shape-validated Core safe-error metadata.

    This class validates protocol structure and returns defensive copies. A
    Host remains responsible for redacting secrets and private values before it
    constructs the object; shape validation cannot prove a message is safe.
    """

    code: str
    message: str
    payload_json: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SafeError:
        """Parse one schema-shaped Core safe-error object."""
        value = _object(payload, "Safe error")
        _allowed_keys(
            value,
            {
                "code",
                "message",
                "retryable",
                "phase",
                "json_pointer",
                "constraint",
                "cause_code",
                "responsibility",
                "operator_correlation_id",
                "recovery",
            },
            {"code", "message"},
            "Safe error",
        )
        code = value["code"]
        if not isinstance(code, str) or not _ERROR_CODE_RE.fullmatch(code):
            raise RunValidationError("Safe error code is invalid.")
        message = _bounded_text(value["message"], "Safe error message", 1, 4000)
        if "retryable" in value and not isinstance(value["retryable"], bool):
            raise RunValidationError("Safe error retryable must be boolean.")
        if "phase" in value:
            _bounded_text(value["phase"], "Safe error phase", 1, 120)
        if "json_pointer" in value:
            _bounded_text(value["json_pointer"], "Safe error json_pointer", 0, 1024)
        for field in ("constraint", "cause_code"):
            if field in value:
                _bounded_text(value[field], f"Safe error {field}", 0, 240)
        if "responsibility" in value and (
            not isinstance(value["responsibility"], str)
            or value["responsibility"] not in _RESPONSIBILITIES
        ):
            raise RunValidationError("Safe error responsibility is invalid.")
        if "operator_correlation_id" in value:
            _opaque_id(value["operator_correlation_id"], "operator_correlation_id")
        if "recovery" in value:
            _validate_recovery(value["recovery"])
        return cls(
            code=code, message=message, payload_json=_json_object(value, "Safe error")
        )

    def payload(self) -> dict[str, Any]:
        """Return a defensive Core safe-error payload copy."""
        return _decode_object(self.payload_json)

    @property
    def retryable(self) -> bool | None:
        """Return the declared retry hint without treating it as authorization."""
        value = self.payload().get("retryable")
        return cast(bool | None, value)


@dataclass(frozen=True)
class RunResult:
    """Immutable Agent terminal proposal after Core shape validation."""

    status: str
    summary: str
    output_json: str | None
    artifact_receipt_ids: tuple[str, ...]
    error: SafeError | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RunResult:
        """Parse one schema-shaped `run.result` payload."""
        value = _object(payload, "Run result")
        _allowed_keys(
            value,
            {"status", "summary", "output", "artifact_receipt_ids", "error"},
            {"status", "summary"},
            "Run result",
        )
        status = value["status"]
        if not isinstance(status, str) or status not in _RESULT_STATES:
            raise RunValidationError("Run result status is invalid.")
        summary = _bounded_text(value["summary"], "Run result summary", 1, 4000)
        has_output = "output" in value
        output_json = (
            _json_value(value["output"], "Run result output") if has_output else None
        )
        receipt_ids = _receipt_ids(value.get("artifact_receipt_ids", []))
        safe_error = (
            SafeError.from_payload(_object(value["error"], "Run result error"))
            if "error" in value
            else None
        )
        if status == "succeeded":
            if not has_output:
                raise RunValidationError("Successful Run result requires output.")
            if safe_error is not None:
                raise RunValidationError(
                    "Successful Run result cannot contain an error."
                )
        elif safe_error is None:
            raise RunValidationError("Non-success Run result requires a safe error.")
        return cls(status, summary, output_json, receipt_ids, safe_error)

    @property
    def output(self) -> Any | None:
        """Return a defensive decoded output value when the proposal supplied one."""
        if self.output_json is None:
            return None
        return json.loads(self.output_json)

    @property
    def has_output(self) -> bool:
        """Return whether the proposal contained an output key, including JSON null."""
        return self.output_json is not None

    def payload(self) -> dict[str, Any]:
        """Return a defensive Core `run.result` payload copy."""
        value: dict[str, Any] = {"status": self.status, "summary": self.summary}
        if self.output_json is not None:
            value["output"] = self.output
        if self.artifact_receipt_ids:
            value["artifact_receipt_ids"] = list(self.artifact_receipt_ids)
        if self.error is not None:
            value["error"] = self.error.payload()
        return value


@dataclass(frozen=True)
class RunTransition:
    """One immutable Host-authoritative state transition or same-state event."""

    event_id: str
    event_type: str
    actor: str
    prior_state: str
    state: str
    recorded_at: str


@dataclass(frozen=True)
class TerminalRecord:
    """One immutable authoritative terminal outcome for a Run."""

    ledger_record_id: str
    transition: RunTransition
    result: RunResult

    @property
    def status(self) -> str:
        """Return the immutable terminal status."""
        return self.result.status

    @property
    def retry_permitted(self) -> bool:
        """Return a conservative retry hint for the completed Run outcome."""
        if self.status in {"succeeded", "cancelled", "indeterminate"}:
            return False
        return self.result.error is not None and self.result.error.retryable is True

    @property
    def requires_reconciliation(self) -> bool:
        """Return whether the original Run ended without a provable outcome."""
        return self.status == "indeterminate"

    def payload(self) -> dict[str, Any]:
        """Return a defensive diagnostic representation without storage details."""
        return {
            "ledger_record_id": self.ledger_record_id,
            "terminal_status": self.status,
            "result": self.result.payload(),
        }


@dataclass(frozen=True)
class TerminalAck:
    """Reference representation of a Host `run.result.ack` response."""

    terminal_status: str
    ledger_record_id: str
    recorded_at: str

    def payload(self) -> dict[str, str]:
        """Return the schema-shaped terminal acknowledgement payload."""
        return {
            "terminal_status": self.terminal_status,
            "ledger_record_id": self.ledger_record_id,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True)
class RunAnomaly:
    """Record one later event that could not rewrite immutable terminal history."""

    event_id: str
    event_type: str
    observed_state: str
    reason: str
    recorded_at: str


@dataclass(frozen=True)
class RunSnapshot:
    """Expose safe Run-ledger facts for recovery and operator diagnostics."""

    scope: ArtifactScope
    state: str
    terminal_ledger_record_id: str | None
    transition_count: int
    anomaly_count: int


@dataclass(frozen=True)
class _EventRecord:
    """Store one accepted idempotency identity and its immutable outcome."""

    event_type: str
    fingerprint: str
    outcome: object


@dataclass(frozen=True)
class _RejectedEvent:
    """Store one deduplicated late-event anomaly identity."""

    event_type: str
    fingerprint: str
    anomaly: RunAnomaly


class RunLedger:
    """Apply Core 0.2 Host-owned Run state and terminal rules for one scope.

    The caller authenticates peers, validates the full Core envelope, and
    persists this state with Artifact and outbound-ack records under its own
    durable transaction. This in-memory reference is thread-safe within one
    process only and intentionally cannot coordinate competing Host processes.
    """

    def __init__(
        self,
        scope: ArtifactScope,
        *,
        artifact_ledger: ArtifactLedger | None = None,
        effect_ledger: EffectLedger | None = None,
    ) -> None:
        """Create an initially queued Host Run ledger.

        Args:
            scope: Host-issued tenant and Run identity, never Agent input.
            artifact_ledger: Optional same-scope Artifact receipt validator.
            effect_ledger: Optional same-scope external Effect settlement gate.

        Raises:
            RunValidationError: If scope or Artifact ownership is invalid.
        """
        if not isinstance(scope, ArtifactScope):
            raise RunValidationError("Run scope must be Host-issued.")
        if artifact_ledger is not None:
            if not isinstance(artifact_ledger, ArtifactLedger):
                raise RunValidationError("Artifact ledger is invalid.")
            if artifact_ledger.scope != scope:
                raise RunValidationError("Artifact ledger must match the Run scope.")
        if effect_ledger is not None:
            if not isinstance(effect_ledger, EffectLedger):
                raise RunValidationError("Effect ledger is invalid.")
            if effect_ledger.scope != scope:
                raise RunValidationError("Effect ledger must match the Run scope.")
        self._scope = scope
        self._artifact_ledger = artifact_ledger
        self._effect_ledger = effect_ledger
        self._state = "queued"
        self._terminal: TerminalRecord | None = None
        self._events: dict[str, _EventRecord] = {}
        self._rejected_events: dict[str, _RejectedEvent] = {}
        self._transitions: list[RunTransition] = []
        self._anomalies: list[RunAnomaly] = []
        self._lock = threading.RLock()

    @property
    def scope(self) -> ArtifactScope:
        """Return the immutable Host-issued Run scope."""
        return self._scope

    @property
    def state(self) -> str:
        """Return the current authoritative Run state."""
        with self._lock:
            return self._state

    def start(self, event_id: str) -> RunTransition:
        """Record the Host `run.start` transition from queued to starting."""
        return self._transition(
            event_id,
            event_type="run.start",
            actor="host",
            payload={},
            allowed_states={"queued"},
            next_state="starting",
        )

    def accept(self, event_id: str) -> RunTransition:
        """Record the Agent `run.accepted` transition from starting to running."""
        return self._transition(
            event_id,
            event_type="run.accepted",
            actor="agent",
            payload={},
            allowed_states={"starting"},
            next_state="running",
        )

    def request_input(self, event_id: str, request_id: str) -> RunTransition:
        """Record one Agent input request and enter `input_required`."""
        return self._transition(
            event_id,
            event_type="run.input_required",
            actor="agent",
            payload={"request_id": _opaque_id(request_id, "request_id")},
            allowed_states={"running"},
            next_state="input_required",
        )

    def respond_input(self, event_id: str, request_id: str) -> RunTransition:
        """Record one Host input response and return the Run to `running`."""
        return self._transition(
            event_id,
            event_type="run.input_response",
            actor="host",
            payload={"request_id": _opaque_id(request_id, "request_id")},
            allowed_states={"input_required"},
            next_state="running",
        )

    def begin_reconciliation(self, event_id: str, reason: str) -> RunTransition:
        """Enter `reconciling` for a Profile-owned uncertain external outcome."""
        return self._transition(
            event_id,
            event_type="effect.reconciling",
            actor="host",
            payload={"reason": _bounded_text(reason, "reconciliation reason", 1, 400)},
            allowed_states={"running"},
            next_state="reconciling",
        )

    def request_cancel(self, event_id: str, reason: str) -> RunTransition:
        """Record a Host cancellation request without assuming work has stopped."""
        return self._transition(
            event_id,
            event_type="run.cancel",
            actor="host",
            payload={"reason": _bounded_text(reason, "cancellation reason", 1, 400)},
            allowed_states=_ACTIVE_STATES,
            next_state=None,
        )

    def record_cancelled(
        self,
        event_id: str,
        *,
        reason: str,
        error: Mapping[str, Any] | None = None,
    ) -> TerminalRecord:
        """Record Agent cancellation confirmation as the first immutable terminal."""
        summary = _bounded_text(reason, "cancellation reason", 1, 400)
        safe_error = (
            SafeError.from_payload(_object(error, "Run cancelled error"))
            if error is not None
            else None
        )
        result = RunResult(
            status="cancelled",
            summary=summary,
            output_json=None,
            artifact_receipt_ids=(),
            error=safe_error,
        )
        payload: dict[str, Any] = {"reason": summary}
        if safe_error is not None:
            payload["error"] = safe_error.payload()
        return self._terminal_transition(
            event_id,
            event_type="run.cancelled",
            actor="agent",
            payload=payload,
            result=result,
            allowed_states=_ACTIVE_STATES,
            validate_artifacts=False,
            validate_effects=False,
        )

    def record_result(
        self, event_id: str, payload: Mapping[str, Any]
    ) -> TerminalRecord:
        """Validate and persist one Agent `run.result` terminal proposal."""
        result = RunResult.from_payload(payload)
        return self._terminal_transition(
            event_id,
            event_type="run.result",
            actor="agent",
            payload=result.payload(),
            result=result,
            allowed_states={
                "running",
                "input_required",
                "approval_required",
                "reconciling",
            },
            validate_artifacts=True,
            validate_effects=True,
        )

    def acknowledge_terminal(self, event_id: str) -> TerminalAck:
        """Return one idempotent Host acknowledgement after a terminal record exists."""
        identifier = _opaque_id(event_id, "event_id")
        with self._lock:
            if self._terminal is None:
                raise RunStateError(
                    "A terminal acknowledgement requires a terminal record."
                )
            payload = {
                "terminal_status": self._terminal.status,
                "ledger_record_id": self._terminal.ledger_record_id,
            }
            fingerprint = _event_fingerprint(
                "run.result.ack", _json_object(payload, "ACK")
            )
            existing = self._existing_outcome(
                identifier,
                "run.result.ack",
                fingerprint,
                allow_after_terminal=True,
            )
            if existing is not None:
                if not isinstance(existing, TerminalAck):
                    raise RunConflictError(
                        "Event ID is already bound to another outcome."
                    )
                return existing
            acknowledgement = TerminalAck(
                terminal_status=self._terminal.status,
                ledger_record_id=self._terminal.ledger_record_id,
                recorded_at=_timestamp(),
            )
            self._events[identifier] = _EventRecord(
                "run.result.ack", fingerprint, acknowledgement
            )
            return acknowledgement

    def terminal(self) -> TerminalRecord | None:
        """Return the immutable terminal record once one has been written."""
        with self._lock:
            return self._terminal

    def transitions(self) -> tuple[RunTransition, ...]:
        """Return the append-only accepted transition history."""
        with self._lock:
            return tuple(self._transitions)

    def anomalies(self) -> tuple[RunAnomaly, ...]:
        """Return later events retained without allowing a terminal rewrite."""
        with self._lock:
            return tuple(self._anomalies)

    def snapshot(self) -> RunSnapshot:
        """Return safe Run facts for resume and operator diagnostics."""
        with self._lock:
            return RunSnapshot(
                scope=self._scope,
                state=self._state,
                terminal_ledger_record_id=(
                    self._terminal.ledger_record_id
                    if self._terminal is not None
                    else None
                ),
                transition_count=len(self._transitions),
                anomaly_count=len(self._anomalies),
            )

    def _transition(
        self,
        event_id: str,
        *,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
        allowed_states: frozenset[str] | set[str],
        next_state: str | None,
    ) -> RunTransition:
        """Apply one legal nonterminal transition or return its exact replay."""
        identifier = _opaque_id(event_id, "event_id")
        fingerprint = _event_fingerprint(event_type, _json_object(payload, event_type))
        with self._lock:
            existing = self._existing_outcome(identifier, event_type, fingerprint)
            if existing is not None:
                if not isinstance(existing, RunTransition):
                    raise RunConflictError(
                        "Event ID is already bound to another outcome."
                    )
                return existing
            self._require_state(allowed_states, event_type)
            transition = RunTransition(
                event_id=identifier,
                event_type=event_type,
                actor=actor,
                prior_state=self._state,
                state=self._state if next_state is None else next_state,
                recorded_at=_timestamp(),
            )
            self._state = transition.state
            self._transitions.append(transition)
            self._events[identifier] = _EventRecord(event_type, fingerprint, transition)
            return transition

    def _terminal_transition(
        self,
        event_id: str,
        *,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
        result: RunResult,
        allowed_states: frozenset[str] | set[str],
        validate_artifacts: bool,
        validate_effects: bool,
    ) -> TerminalRecord:
        """Write exactly one terminal record after all semantic gates pass."""
        identifier = _opaque_id(event_id, "event_id")
        fingerprint = _event_fingerprint(event_type, _json_object(payload, event_type))
        with self._lock:
            existing = self._existing_outcome(identifier, event_type, fingerprint)
            if existing is not None:
                if not isinstance(existing, TerminalRecord):
                    raise RunConflictError(
                        "Event ID is already bound to another outcome."
                    )
                return existing
            self._require_state(allowed_states, event_type)
            if validate_artifacts:
                self._validate_result_artifacts(result)
            if validate_effects:
                self._validate_result_effects(result)
            transition = RunTransition(
                event_id=identifier,
                event_type=event_type,
                actor=actor,
                prior_state=self._state,
                state=result.status,
                recorded_at=_timestamp(),
            )
            terminal = TerminalRecord(
                ledger_record_id=f"run-record-{secrets.token_urlsafe(18)}",
                transition=transition,
                result=result,
            )
            self._state = result.status
            self._terminal = terminal
            self._transitions.append(transition)
            self._events[identifier] = _EventRecord(event_type, fingerprint, terminal)
            return terminal

    def _validate_result_artifacts(self, result: RunResult) -> None:
        """Gate all result receipt references through the same-scope ledger."""
        if self._artifact_ledger is None:
            if result.artifact_receipt_ids:
                raise RunValidationError(
                    "Run result cannot reference Artifacts without a Host receipt ledger."
                )
            return
        if result.status == "succeeded":
            self._artifact_ledger.validate_success(result.artifact_receipt_ids)
        else:
            self._artifact_ledger.validate_receipts(result.artifact_receipt_ids)

    def _validate_result_effects(self, result: RunResult) -> None:
        """Gate successful terminal state on every required Profile Effect settlement."""
        if result.status == "succeeded" and self._effect_ledger is not None:
            self._effect_ledger.validate_success()

    def _existing_outcome(
        self,
        event_id: str,
        event_type: str,
        fingerprint: str,
        *,
        allow_after_terminal: bool = False,
    ) -> object | None:
        """Return an exact accepted replay or reject conflicting/late identities."""
        existing = self._events.get(event_id)
        if existing is not None:
            if existing.event_type != event_type or existing.fingerprint != fingerprint:
                raise RunConflictError(
                    "Event ID was reused with different immutable data."
                )
            return existing.outcome
        rejected = self._rejected_events.get(event_id)
        if rejected is not None:
            if rejected.event_type != event_type or rejected.fingerprint != fingerprint:
                raise RunConflictError(
                    "Event ID was reused with different immutable data."
                )
            raise RunTerminalConflictError(
                "Run already has an authoritative terminal record."
            )
        if self._terminal is not None and not allow_after_terminal:
            anomaly = RunAnomaly(
                event_id=event_id,
                event_type=event_type,
                observed_state=self._state,
                reason="terminal_record_already_exists",
                recorded_at=_timestamp(),
            )
            self._anomalies.append(anomaly)
            self._rejected_events[event_id] = _RejectedEvent(
                event_type, fingerprint, anomaly
            )
            raise RunTerminalConflictError(
                "Run already has an authoritative terminal record."
            )
        return None

    def _require_state(
        self, allowed_states: frozenset[str] | set[str], event_type: str
    ) -> None:
        """Reject a legal message type applied from an illegal prior Run state."""
        if self._state not in allowed_states:
            raise RunStateError(
                f"{event_type} is not legal while the Run is {self._state}."
            )


def _object(value: Any, label: str) -> Mapping[str, Any]:
    """Require one JSON-object-shaped value with string keys."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RunValidationError(f"{label} must be a JSON object.")
    return cast(Mapping[str, Any], value)


def _allowed_keys(
    value: Mapping[str, Any],
    allowed: set[str],
    required: set[str],
    label: str,
) -> None:
    """Require all mandatory fields and reject undeclared Core fields."""
    if not required <= set(value) or set(value) - allowed:
        raise RunValidationError(f"{label} has missing or unsupported fields.")


def _opaque_id(value: Any, label: str) -> str:
    """Validate one bounded, valid-UTF-8 opaque protocol identifier."""
    if not isinstance(value, str) or not value:
        raise RunValidationError(f"{label} must be a non-empty string.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RunValidationError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise RunValidationError(f"{label} must be at most 240 bytes.")
    return value


def _bounded_text(value: Any, label: str, minimum: int, maximum: int) -> str:
    """Validate one Core bounded text field using Schema character limits."""
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise RunValidationError(f"{label} is invalid.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RunValidationError(f"{label} must be valid UTF-8 text.") from exc
    return value


def _receipt_ids(value: Any) -> tuple[str, ...]:
    """Validate the JSON-array-only Artifact receipt reference field."""
    if not isinstance(value, list):
        raise RunValidationError("Artifact receipt IDs must be a JSON array.")
    result = tuple(_opaque_id(item, "artifact_receipt_id") for item in value)
    if len(result) != len(set(result)):
        raise RunValidationError("Artifact receipt IDs must be unique.")
    return result


def _validate_recovery(value: Any) -> None:
    """Validate the optional structured recovery object in a safe error."""
    recovery = _object(value, "Safe error recovery")
    _allowed_keys(
        recovery, {"action", "retry_after_ms"}, {"action"}, "Safe error recovery"
    )
    _bounded_text(recovery["action"], "Safe error recovery action", 1, 240)
    if "retry_after_ms" in recovery:
        retry_after = recovery["retry_after_ms"]
        if (
            isinstance(retry_after, bool)
            or not isinstance(retry_after, int)
            or retry_after < 0
        ):
            raise RunValidationError("Safe error retry_after_ms is invalid.")


def _json_value(value: Any, label: str) -> str:
    """Encode one finite JSON value into a deterministic defensive snapshot."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        encoded.encode("utf-8")
        json.loads(encoded)
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise RunValidationError(f"{label} must contain finite JSON values.") from exc
    return encoded


def _json_object(value: Mapping[str, Any], label: str) -> str:
    """Encode one already object-shaped value into a deterministic snapshot."""
    encoded = _json_value(dict(value), label)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise RunValidationError(f"{label} must be a JSON object.")
    return encoded


def _decode_object(value: str) -> dict[str, Any]:
    """Decode one internally canonicalized JSON object as a fresh dictionary."""
    decoded = json.loads(value)
    return cast(dict[str, Any], decoded)


def _event_fingerprint(event_type: str, payload_json: str) -> str:
    """Return a domain-separated duplicate identity for one event payload."""
    digest = hashlib.sha256()
    digest.update(_FINGERPRINT_DOMAIN)
    digest.update(event_type.encode("utf-8"))
    digest.update(b"\n")
    digest.update(payload_json.encode("utf-8"))
    return digest.hexdigest()


def _timestamp() -> str:
    """Return a UTC RFC 3339 timestamp for a reference-ledger audit record."""
    value = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return value.replace("+00:00", "Z")
