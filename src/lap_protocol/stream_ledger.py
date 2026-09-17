"""Reference state machine for LAP Core 0.2 stream reliability.

The ledger deliberately owns protocol invariants, not transport, identity, or
storage. A Host must atomically persist an exported checkpoint before it sends
an ACK or applies a business side effect. The in-memory implementation makes
those transition rules executable and portable without claiming that memory is
durable storage.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, cast

_CHECKPOINT_FORMAT: Final = "lap-core-0.2-stream-ledger"
_CHECKPOINT_VERSION: Final = 1
_EVENT_FINGERPRINT_DOMAIN: Final = b"LAP-CORE-0.2-STREAM-EVENT\n"


class StreamLedgerError(ValueError):
    """Base class for safe, deterministic Core 0.2 stream failures."""


class InvalidStreamEventError(StreamLedgerError):
    """Raised when an event, epoch, sequence, or replay bound is invalid."""


class EpochError(StreamLedgerError):
    """Raised when a writer does not hold the active epoch lease."""


class StaleEpochError(EpochError):
    """Raised when a fenced writer attempts to append a frame."""


class SequenceGapError(StreamLedgerError):
    """Raised when a frame skips an unapplied sequence number."""


class SequenceConflictError(StreamLedgerError):
    """Raised when one stream position is reused for different content."""


class AckRangeError(StreamLedgerError):
    """Raised when an ACK claims a sequence that was not applied."""


class ReplayUnavailableError(StreamLedgerError):
    """Raised when bounded retention cannot supply the requested replay."""


class CheckpointError(StreamLedgerError):
    """Raised when a persisted reference-ledger checkpoint is malformed."""


@dataclass(frozen=True)
class StreamEvent:
    """One accepted stream position with an immutable JSON payload snapshot.

    ``payload_json`` is an internal deterministic representation used only to
    detect same-position conflicts in this reference implementation. It is not
    the RFC 8785 release or capability canonicalization mechanism.
    """

    stream_id: str
    epoch: int
    seq: int
    event_id: str
    payload_json: str
    fingerprint: str

    @property
    def payload(self) -> dict[str, Any]:
        """Return a defensive JSON object copy of the accepted payload."""
        value = json.loads(self.payload_json)
        assert isinstance(value, dict)
        return value

    def checkpoint_record(self) -> dict[str, Any]:
        """Return the JSON-safe event representation used in a checkpoint."""
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "payload": self.payload,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ApplyResult:
    """Describe whether a received frame changed ledger state."""

    disposition: str
    event: StreamEvent


@dataclass(frozen=True)
class AckResult:
    """Describe the contiguous durable-application waterline update."""

    epoch: int
    ack_seq: int
    advanced: bool


@dataclass(frozen=True)
class ReplayResult:
    """Return one bounded replay page and its continuation waterline."""

    epoch: int
    events: tuple[StreamEvent, ...]
    next_after_seq: int
    complete: bool


@dataclass(frozen=True)
class StreamSnapshot:
    """Expose safe state required for resume and operator diagnostics."""

    stream_id: str
    epoch: int
    last_applied_seq: int
    last_acked_seq: int
    replay_available_from_seq: int
    replay_available: bool


@dataclass(frozen=True)
class _EventIdentity:
    """Store a durable duplicate-detection identity independent of replay bytes."""

    event_id: str
    fingerprint: str


@dataclass
class _EpochState:
    """Keep one writer epoch's append, ACK, replay, and duplicate state."""

    last_applied_seq: int = 0
    last_acked_seq: int = 0
    events: dict[int, StreamEvent] = field(default_factory=dict)
    identities: dict[int, _EventIdentity] = field(default_factory=dict)


class StreamLedger:
    """Apply Core 0.2 stream ordering and replay rules for one stream.

    The caller must authenticate peers, validate the Core envelope, and
    persist ``export_state()`` under its own transaction before sending an ACK.
    The ledger is thread-safe inside one process; it intentionally does not
    coordinate multiple Host processes or substitute for a durable database.
    """

    def __init__(
        self,
        stream_id: str,
        *,
        retention_events: int = 256,
        max_replay_events: int | None = None,
    ) -> None:
        """Create an empty ledger with explicit bounded replay limits.

        Args:
            stream_id: Host-issued Core stream identity.
            retention_events: Maximum replayable event bodies retained per epoch.
            max_replay_events: Maximum events returned by one replay page.

        Raises:
            InvalidStreamEventError: If identifiers or replay limits are invalid.
        """
        self._stream_id = _opaque_id(stream_id, "stream_id")
        self._retention_events = _positive_int(retention_events, "retention_events")
        page_limit = (
            self._retention_events
            if max_replay_events is None
            else _positive_int(max_replay_events, "max_replay_events")
        )
        if page_limit > self._retention_events:
            raise InvalidStreamEventError(
                "max_replay_events must not exceed retention_events."
            )
        self._max_replay_events = page_limit
        self._current_epoch = 0
        self._epochs: dict[int, _EpochState] = {}
        self._lock = threading.RLock()

    @property
    def stream_id(self) -> str:
        """Return the immutable stream identity."""
        return self._stream_id

    def acquire_epoch(self, epoch: int) -> StreamSnapshot:
        """Acquire the next writer epoch and fence all older writers.

        Repeating the current epoch is an idempotent lease-response replay. A
        new epoch must advance exactly one step so a restored ledger cannot
        silently skip a writer generation.
        """
        requested_epoch = _positive_int(epoch, "epoch")
        with self._lock:
            if requested_epoch == self._current_epoch:
                return self.snapshot()
            expected_epoch = self._current_epoch + 1
            if requested_epoch != expected_epoch:
                raise EpochError(
                    f"Expected writer epoch {expected_epoch}, received {requested_epoch}."
                )
            self._current_epoch = requested_epoch
            self._epochs[requested_epoch] = _EpochState()
            return self.snapshot()

    def apply(
        self,
        *,
        epoch: int,
        seq: int,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> ApplyResult:
        """Apply one validated frame or return its prior idempotent outcome.

        A sequence is accepted only once. A replay at the same position must
        have the exact event identity and payload fingerprint; otherwise the
        Host must stop rather than guessing which frame is authoritative.
        """
        requested_epoch = _positive_int(epoch, "epoch")
        requested_seq = _positive_int(seq, "seq")
        accepted_event_id = _opaque_id(event_id, "event_id")
        payload_json = _payload_json(payload)
        fingerprint = _event_fingerprint(accepted_event_id, payload_json)
        event = StreamEvent(
            stream_id=self._stream_id,
            epoch=requested_epoch,
            seq=requested_seq,
            event_id=accepted_event_id,
            payload_json=payload_json,
            fingerprint=fingerprint,
        )

        with self._lock:
            state = self._active_epoch(requested_epoch)
            existing = state.identities.get(requested_seq)
            if existing is not None:
                if existing != _EventIdentity(accepted_event_id, fingerprint):
                    raise SequenceConflictError(
                        "A stream position was replayed with different event content."
                    )
                return ApplyResult(disposition="duplicate", event=event)

            expected_seq = state.last_applied_seq + 1
            if requested_seq < expected_seq:
                raise SequenceConflictError(
                    "A prior stream position has no durable duplicate identity."
                )
            if requested_seq > expected_seq:
                raise SequenceGapError(
                    f"Expected sequence {expected_seq}, received {requested_seq}."
                )

            state.last_applied_seq = requested_seq
            state.identities[requested_seq] = _EventIdentity(
                accepted_event_id, fingerprint
            )
            state.events[requested_seq] = event
            self._prune_replay_events(state)
            return ApplyResult(disposition="applied", event=event)

    def acknowledge(self, *, epoch: int, seq: int) -> AckResult:
        """Record a contiguous applied-through waterline for one known epoch.

        A delayed ACK for a prior known epoch is safe to retain for audit and
        replay accounting, but it never reactivates that writer epoch.
        """
        requested_epoch = _positive_int(epoch, "epoch")
        acknowledged_seq = _nonnegative_int(seq, "seq")
        with self._lock:
            state = self._known_epoch(requested_epoch)
            if acknowledged_seq > state.last_applied_seq:
                raise AckRangeError(
                    "An ACK cannot advance beyond durably applied sequence."
                )
            if acknowledged_seq <= state.last_acked_seq:
                return AckResult(
                    epoch=requested_epoch,
                    ack_seq=state.last_acked_seq,
                    advanced=False,
                )
            state.last_acked_seq = acknowledged_seq
            return AckResult(
                epoch=requested_epoch,
                ack_seq=acknowledged_seq,
                advanced=True,
            )

    def replay(
        self,
        *,
        epoch: int,
        after_seq: int,
        limit: int | None = None,
    ) -> ReplayResult:
        """Return a bounded page of retained events after one ACK waterline.

        Raises ``ReplayUnavailableError`` instead of silently omitting an event
        when a requested waterline predates retained frame bodies.
        """
        requested_epoch = _positive_int(epoch, "epoch")
        waterline = _nonnegative_int(after_seq, "after_seq")
        page_size = (
            self._max_replay_events if limit is None else _positive_int(limit, "limit")
        )
        if page_size > self._max_replay_events:
            raise InvalidStreamEventError(
                "Replay limit exceeds the negotiated stream page limit."
            )
        with self._lock:
            state = self._known_epoch(requested_epoch)
            if waterline > state.last_applied_seq:
                raise InvalidStreamEventError(
                    "Replay waterline cannot exceed the applied sequence."
                )
            replay_available_from = _replay_available_from(state)
            if waterline < replay_available_from:
                raise ReplayUnavailableError(
                    "Replay retention no longer covers the requested waterline."
                )
            events = tuple(
                event
                for sequence, event in state.events.items()
                if sequence > waterline
            )[:page_size]
            next_after_seq = events[-1].seq if events else waterline
            return ReplayResult(
                epoch=requested_epoch,
                events=events,
                next_after_seq=next_after_seq,
                complete=next_after_seq == state.last_applied_seq,
            )

    def snapshot(self, *, epoch: int | None = None) -> StreamSnapshot:
        """Return the latest safe resume facts for one ledger epoch."""
        with self._lock:
            selected_epoch = (
                self._current_epoch if epoch is None else _positive_int(epoch, "epoch")
            )
            if selected_epoch == 0:
                return StreamSnapshot(
                    stream_id=self._stream_id,
                    epoch=0,
                    last_applied_seq=0,
                    last_acked_seq=0,
                    replay_available_from_seq=0,
                    replay_available=True,
                )
            state = self._known_epoch(selected_epoch)
            replay_available_from = _replay_available_from(state)
            return StreamSnapshot(
                stream_id=self._stream_id,
                epoch=selected_epoch,
                last_applied_seq=state.last_applied_seq,
                last_acked_seq=state.last_acked_seq,
                replay_available_from_seq=replay_available_from,
                replay_available=state.last_acked_seq >= replay_available_from,
            )

    def export_state(self) -> dict[str, Any]:
        """Return a JSON-safe checkpoint for a Host-owned durable transaction."""
        with self._lock:
            return {
                "format": _CHECKPOINT_FORMAT,
                "version": _CHECKPOINT_VERSION,
                "stream_id": self._stream_id,
                "retention_events": self._retention_events,
                "max_replay_events": self._max_replay_events,
                "current_epoch": self._current_epoch,
                "epochs": [
                    self._checkpoint_epoch(epoch, state)
                    for epoch, state in self._epochs.items()
                ],
            }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> StreamLedger:
        """Restore a ledger checkpoint after validating all protocol invariants."""
        if not isinstance(state, Mapping):
            raise CheckpointError("Stream ledger checkpoint must be a JSON object.")
        if state.get("format") != _CHECKPOINT_FORMAT:
            raise CheckpointError("Stream ledger checkpoint format is unsupported.")
        if state.get("version") != _CHECKPOINT_VERSION:
            raise CheckpointError("Stream ledger checkpoint version is unsupported.")
        try:
            ledger = cls(
                _opaque_id(state["stream_id"], "stream_id"),
                retention_events=_positive_int(
                    state["retention_events"], "retention_events"
                ),
                max_replay_events=_positive_int(
                    state["max_replay_events"], "max_replay_events"
                ),
            )
            current_epoch = _nonnegative_int(state["current_epoch"], "current_epoch")
            epoch_records = state["epochs"]
        except (KeyError, InvalidStreamEventError) as exc:
            raise CheckpointError(
                "Stream ledger checkpoint is missing valid metadata."
            ) from exc
        if not isinstance(epoch_records, list) or len(epoch_records) != current_epoch:
            raise CheckpointError(
                "Stream ledger checkpoint has an invalid epoch history."
            )

        for expected_epoch, record in enumerate(epoch_records, start=1):
            ledger._restore_epoch(expected_epoch, record)
        ledger._current_epoch = current_epoch
        return ledger

    def _active_epoch(self, epoch: int) -> _EpochState:
        if epoch < self._current_epoch:
            raise StaleEpochError("The writer epoch is fenced by a newer lease.")
        if epoch > self._current_epoch or epoch == 0:
            raise EpochError("The writer epoch has not been acquired.")
        return self._epochs[epoch]

    def _known_epoch(self, epoch: int) -> _EpochState:
        try:
            return self._epochs[epoch]
        except KeyError as exc:
            raise EpochError(
                "The requested epoch is not known to this stream."
            ) from exc

    def _prune_replay_events(self, state: _EpochState) -> None:
        while len(state.events) > self._retention_events:
            oldest_sequence = next(iter(state.events))
            del state.events[oldest_sequence]

    def _checkpoint_epoch(self, epoch: int, state: _EpochState) -> dict[str, Any]:
        return {
            "epoch": epoch,
            "last_applied_seq": state.last_applied_seq,
            "last_acked_seq": state.last_acked_seq,
            "identities": [
                {
                    "seq": sequence,
                    "event_id": identity.event_id,
                    "fingerprint": identity.fingerprint,
                }
                for sequence, identity in state.identities.items()
            ],
            "events": [event.checkpoint_record() for event in state.events.values()],
        }

    def _restore_epoch(self, expected_epoch: int, record: Any) -> None:
        if not isinstance(record, Mapping):
            raise CheckpointError("Stream ledger epoch record must be a JSON object.")
        try:
            epoch = _positive_int(record["epoch"], "epoch")
            last_applied_seq = _nonnegative_int(
                record["last_applied_seq"], "last_applied_seq"
            )
            last_acked_seq = _nonnegative_int(
                record["last_acked_seq"], "last_acked_seq"
            )
            identities = record["identities"]
            events = record["events"]
        except (KeyError, InvalidStreamEventError) as exc:
            raise CheckpointError(
                "Stream ledger epoch record is missing valid metadata."
            ) from exc
        if epoch != expected_epoch or last_acked_seq > last_applied_seq:
            raise CheckpointError("Stream ledger epoch waterlines are inconsistent.")
        if not isinstance(identities, list) or not isinstance(events, list):
            raise CheckpointError("Stream ledger epoch collections must be arrays.")
        if len(identities) != last_applied_seq:
            raise CheckpointError("Stream ledger duplicate identities are incomplete.")

        restored = _EpochState(
            last_applied_seq=last_applied_seq,
            last_acked_seq=last_acked_seq,
        )
        for expected_seq, identity_record in enumerate(identities, start=1):
            identity = _restore_identity(expected_seq, identity_record)
            restored.identities[expected_seq] = identity

        expected_event_sequences = list(
            range(
                max(1, last_applied_seq - self._retention_events + 1),
                last_applied_seq + 1,
            )
        )
        if [
            record.get("seq") if isinstance(record, Mapping) else None
            for record in events
        ] != (expected_event_sequences):
            raise CheckpointError("Stream ledger replay records are not contiguous.")
        for event_record in events:
            event = _restore_event(self._stream_id, epoch, event_record)
            identity = restored.identities[event.seq]
            if identity != _EventIdentity(event.event_id, event.fingerprint):
                raise CheckpointError(
                    "Stream ledger event identity does not match its body."
                )
            restored.events[event.seq] = event
        self._epochs[epoch] = restored


def _opaque_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise InvalidStreamEventError(
            f"{label} must be a non-empty string up to 240 bytes."
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidStreamEventError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise InvalidStreamEventError(
            f"{label} must be a non-empty string up to 240 bytes."
        )
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidStreamEventError(f"{label} must be a positive integer.")
    return cast(int, value)


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidStreamEventError(f"{label} must be a non-negative integer.")
    return cast(int, value)


def _payload_json(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise InvalidStreamEventError("payload must be a JSON object.")
    if not all(isinstance(key, str) for key in payload):
        raise InvalidStreamEventError("payload object keys must be strings.")
    try:
        encoded = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise InvalidStreamEventError(
            "payload must contain only finite JSON values."
        ) from exc
    if not isinstance(decoded, dict):
        raise InvalidStreamEventError("payload must be a JSON object.")
    return encoded


def _event_fingerprint(event_id: str, payload_json: str) -> str:
    digest = hashlib.sha256()
    digest.update(_EVENT_FINGERPRINT_DOMAIN)
    digest.update(event_id.encode("utf-8"))
    digest.update(b"\n")
    digest.update(payload_json.encode("utf-8"))
    return digest.hexdigest()


def _replay_available_from(state: _EpochState) -> int:
    if not state.events:
        return state.last_applied_seq
    return next(iter(state.events)) - 1


def _restore_identity(expected_seq: int, record: Any) -> _EventIdentity:
    if not isinstance(record, Mapping):
        raise CheckpointError("Stream ledger duplicate identity must be a JSON object.")
    try:
        sequence = _positive_int(record["seq"], "seq")
        event_id = _opaque_id(record["event_id"], "event_id")
        fingerprint = _digest(record["fingerprint"], "fingerprint")
    except (KeyError, InvalidStreamEventError) as exc:
        raise CheckpointError("Stream ledger duplicate identity is invalid.") from exc
    if sequence != expected_seq:
        raise CheckpointError("Stream ledger duplicate identities are not contiguous.")
    return _EventIdentity(event_id, fingerprint)


def _restore_event(stream_id: str, epoch: int, record: Any) -> StreamEvent:
    if not isinstance(record, Mapping):
        raise CheckpointError("Stream ledger replay record must be a JSON object.")
    try:
        seq = _positive_int(record["seq"], "seq")
        event_id = _opaque_id(record["event_id"], "event_id")
        payload_json = _payload_json(record["payload"])
        fingerprint = _digest(record["fingerprint"], "fingerprint")
    except (KeyError, InvalidStreamEventError) as exc:
        raise CheckpointError("Stream ledger replay record is invalid.") from exc
    calculated = _event_fingerprint(event_id, payload_json)
    if fingerprint != calculated:
        raise CheckpointError("Stream ledger replay record fingerprint is invalid.")
    return StreamEvent(stream_id, epoch, seq, event_id, payload_json, fingerprint)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise InvalidStreamEventError(f"{label} must be a SHA-256 hexadecimal digest.")
    try:
        int(value, 16)
    except ValueError as exc:
        raise InvalidStreamEventError(
            f"{label} must be a SHA-256 hexadecimal digest."
        ) from exc
    return value
