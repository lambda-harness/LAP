"""Reference ``lap-effect/0.1`` external-effect lifecycle semantics.

The ledger models Host-owned evidence for an external side effect. It separates
an Agent's proposed intent and provider acknowledgement from a verified business
outcome. It is an in-memory reference, not a provider client, grant issuer,
approval system, durable database, or a production reconciliation service.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, TypeVar, cast

from .artifact_ledger import ArtifactScope

_DIGEST_RE: Final = re.compile(r"^sha256:[a-f0-9]{64}$")
_EFFECT_TYPE_RE: Final = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_ERROR_CODE_RE: Final = re.compile(r"^LAP-[1-5][0-9]{2}$")
_TERMINAL_STATES: Final = frozenset(("settled", "failed", "indeterminate"))
_RECONCILIATION_OUTCOMES: Final = _TERMINAL_STATES
_EVENT_DOMAIN: Final = b"LAP-EFFECT-0.1-EVENT\n"
_Outcome = TypeVar("_Outcome")


class EffectLedgerError(ValueError):
    """Represent one safe, typed effect-profile rejection."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the rejection with a stable LAP code and safe message."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class EffectValidationError(EffectLedgerError):
    """Reject malformed effect records, identifiers, or Host configuration."""

    def __init__(self, message: str) -> None:
        """Initialize the effect validation rejection."""
        super().__init__("LAP-201", message)


class EffectStateError(EffectLedgerError):
    """Reject one effect event that is illegal from its current state."""

    def __init__(self, message: str) -> None:
        """Initialize the effect lifecycle-state rejection."""
        super().__init__("LAP-201", message)


class EffectAuthorizationError(EffectLedgerError):
    """Reject an intent outside the Host-admitted capability effect contract."""

    def __init__(self, message: str) -> None:
        """Initialize the capability-scope rejection."""
        super().__init__("LAP-301", message)


class EffectQuotaError(EffectLedgerError):
    """Reject an effect intent exceeding its Host-admitted contract limit."""

    def __init__(self, message: str) -> None:
        """Initialize the bounded-effect policy rejection."""
        super().__init__("LAP-401", message)


class EffectConflictError(EffectLedgerError):
    """Reject changed data under an immutable event, intent, or terminal state."""

    def __init__(self, message: str) -> None:
        """Initialize the immutable-effect conflict rejection."""
        super().__init__("LAP-109", message)


class EffectTerminalConflictError(EffectConflictError):
    """Reject an event that would change an already terminal external effect."""

    def __init__(self, effect_id: str, observed_state: str) -> None:
        """Initialize the terminal conflict with only the public lifecycle state."""
        self.effect_id = effect_id
        self.observed_state = observed_state
        super().__init__("External effect already has an immutable terminal outcome.")


class EffectTerminalGateError(EffectLedgerError):
    """Reject a successful Run while a required external effect lacks settlement."""

    def __init__(self) -> None:
        """Initialize the required-effect settlement gate rejection."""
        super().__init__("LAP-104", "A required external effect has not settled.")


@dataclass(frozen=True)
class EffectIntent:
    """One Agent-proposed, content-addressed request for an external effect."""

    intent_id: str
    effect_type: str
    request_digest: str
    summary: str

    def __post_init__(self) -> None:
        """Defend the public value object against direct invalid construction."""
        _opaque_id(self.intent_id, "intent_id")
        _effect_type(self.effect_type)
        _digest(self.request_digest, "request_digest")
        _bounded_text(self.summary, "Effect summary", 1, 400)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> EffectIntent:
        """Parse one strict, safe `effect.intent`-shaped payload."""
        value = _object(payload, "Effect intent")
        _allowed_keys(
            value,
            {"intent_id", "effect_type", "request_digest", "summary"},
            {"intent_id", "effect_type", "request_digest", "summary"},
            "Effect intent",
        )
        effect_type = _effect_type(value["effect_type"])
        return cls(
            intent_id=_opaque_id(value["intent_id"], "intent_id"),
            effect_type=effect_type,
            request_digest=_digest(value["request_digest"], "request_digest"),
            summary=_bounded_text(value["summary"], "Effect summary", 1, 400),
        )

    def payload(self) -> dict[str, str]:
        """Return a defensive wire-shaped intent representation."""
        return {
            "intent_id": self.intent_id,
            "effect_type": self.effect_type,
            "request_digest": self.request_digest,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class EffectRule:
    """One immutable Host-admitted external-effect contract rule.

    The Host derives every rule from the selected capability release contract,
    rather than accepting it from an Agent intent or ordinary user input.
    """

    effect_type: str
    required_for_success: bool
    approval_required: bool
    max_intents: int = 1

    def __post_init__(self) -> None:
        """Reject an unsafe or ambiguous direct Host policy construction."""
        _effect_type(self.effect_type)
        if not isinstance(self.required_for_success, bool):
            raise EffectValidationError("Effect required policy must be boolean.")
        if not isinstance(self.approval_required, bool):
            raise EffectValidationError("Effect approval policy must be boolean.")
        if (
            isinstance(self.max_intents, bool)
            or not isinstance(self.max_intents, int)
            or not 1 <= self.max_intents <= 1000
        ):
            raise EffectValidationError("Effect maximum intent count is invalid.")


@dataclass(frozen=True)
class EffectRecord:
    """One Host-owned effect record without raw request, credential, or receipt data."""

    effect_id: str
    scope: ArtifactScope
    capability_id: str
    intent: EffectIntent
    required: bool
    approval_required: bool
    state: str
    authorization_ref: str | None
    approval_ref: str | None
    provider_operation_ref: str | None
    evidence_ref: str | None
    failure_code: str | None
    failure_summary: str | None

    @property
    def is_terminal(self) -> bool:
        """Return whether this effect has a final immutable external outcome."""
        return self.state in _TERMINAL_STATES

    @property
    def needs_reconciliation(self) -> bool:
        """Return whether the effect might have occurred but cannot yet be proven."""
        return self.state in {"unknown", "reconciling", "indeterminate"}

    @property
    def retry_permitted(self) -> bool:
        """Return false because a new effect needs a new explicit Host decision."""
        return False

    def payload(self) -> dict[str, Any]:
        """Return safe effect facts suitable for a correlated profile response."""
        value: dict[str, Any] = {
            "effect_id": self.effect_id,
            "intent_id": self.intent.intent_id,
            "effect_type": self.intent.effect_type,
            "request_digest": self.intent.request_digest,
            "summary": self.intent.summary,
            "required": self.required,
            "approval_required": self.approval_required,
            "state": self.state,
        }
        if self.provider_operation_ref is not None:
            value["provider_operation_ref"] = self.provider_operation_ref
        if self.evidence_ref is not None:
            value["evidence_ref"] = self.evidence_ref
        if self.failure_code is not None:
            value["failure_code"] = self.failure_code
        if self.failure_summary is not None:
            value["failure_summary"] = self.failure_summary
        return value


@dataclass(frozen=True)
class EffectTransition:
    """One append-only Host-applied effect lifecycle transition."""

    event_id: str
    event_type: str
    actor: str
    effect_id: str
    prior_state: str
    state: str
    recorded_at: str


@dataclass(frozen=True)
class EffectAnomaly:
    """One late event retained without allowing terminal effect history to change."""

    event_id: str
    event_type: str
    effect_id: str
    observed_state: str
    reason: str
    recorded_at: str


@dataclass(frozen=True)
class EffectSnapshot:
    """Expose Host-safe lifecycle facts for one scoped effect ledger."""

    scope: ArtifactScope
    capability_id: str
    effect_count: int
    transition_count: int
    anomaly_count: int
    unresolved_required_count: int


@dataclass
class _EffectState:
    """Keep mutable in-memory state behind immutable externally returned records."""

    effect_id: str
    intent: EffectIntent
    required: bool
    approval_required: bool
    state: str = "proposed"
    authorization_ref: str | None = None
    approval_ref: str | None = None
    provider_operation_ref: str | None = None
    evidence_ref: str | None = None
    failure_code: str | None = None
    failure_summary: str | None = None


@dataclass(frozen=True)
class _EventRecord:
    """Store one idempotent accepted event identity and its immutable response."""

    event_type: str
    fingerprint: str
    outcome: EffectRecord


@dataclass(frozen=True)
class _RejectedEvent:
    """Store one deduplicated late terminal-event anomaly identity."""

    event_type: str
    fingerprint: str
    anomaly: EffectAnomaly


class EffectLedger:
    """Apply `lap-effect/0.1` Host-owned lifecycle rules for one capability Run.

    The Host supplies an immutable allow-list from the admitted capability's
    Effect contract. It authenticates the Agent/provider, applies approval and
    grant policy, verifies provider evidence, and persists every mutation with
    the Run terminal decision in its own durable transaction.
    """

    def __init__(
        self,
        scope: ArtifactScope,
        capability_id: str,
        rules: Iterable[EffectRule],
    ) -> None:
        """Create an empty ledger bound to one Host-issued scope and capability.

        Args:
            scope: Host-issued tenant and Run scope, never Agent input.
            capability_id: Exact Host-admitted capability that may propose effects.
            rules: Non-empty immutable capability effect contract rules.

        Raises:
            EffectValidationError: If scope or the admitted contract boundary is
                malformed or empty.
        """
        if not isinstance(scope, ArtifactScope):
            raise EffectValidationError("Effect scope must be Host-issued.")
        self._scope = scope
        self._capability_id = _opaque_id(capability_id, "capability_id")
        self._rules_by_type = _effect_rules(rules)
        self._allowed_effect_types = tuple(self._rules_by_type)
        self._effects: dict[str, _EffectState] = {}
        self._intent_ids: dict[str, str] = {}
        self._events: dict[str, _EventRecord] = {}
        self._rejected_events: dict[str, _RejectedEvent] = {}
        self._transitions: list[EffectTransition] = []
        self._anomalies: list[EffectAnomaly] = []
        self._lock = threading.RLock()

    @property
    def scope(self) -> ArtifactScope:
        """Return the immutable Host-issued tenant and Run scope."""
        return self._scope

    @property
    def capability_id(self) -> str:
        """Return the exact Host-admitted capability effect boundary."""
        return self._capability_id

    @property
    def allowed_effect_types(self) -> tuple[str, ...]:
        """Return the deterministic immutable admitted effect-type allow-list."""
        return self._allowed_effect_types

    @property
    def rules(self) -> tuple[EffectRule, ...]:
        """Return the deterministic immutable rules of the admitted capability."""
        return tuple(self._rules_by_type.values())

    def propose(
        self,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> EffectRecord:
        """Record one Agent intent after checking the Host effect contract.

        Requiredness, approval, and count limits come only from the Host-admitted
        rule. The Agent's payload cannot bypass a success or approval gate.
        """
        intent = EffectIntent.from_payload(payload)
        rule = self._rules_by_type.get(intent.effect_type)
        if rule is None:
            raise EffectAuthorizationError(
                "Effect type is not authorized for the admitted capability."
            )
        fingerprint_payload = {"intent": intent.payload()}

        def mutate() -> EffectRecord:
            existing_id = self._intent_ids.get(intent.intent_id)
            if existing_id is not None:
                existing = self._effects[existing_id]
                if existing.intent != intent:
                    raise EffectConflictError(
                        "Effect intent ID is already bound to different data."
                    )
                return self._record(existing)
            existing_count = sum(
                effect.intent.effect_type == intent.effect_type
                for effect in self._effects.values()
            )
            if existing_count >= rule.max_intents:
                raise EffectQuotaError(
                    "Effect intent count exceeds the admitted capability limit."
                )
            effect_id = self._new_effect_id()
            effect = _EffectState(
                effect_id=effect_id,
                intent=intent,
                required=rule.required_for_success,
                approval_required=rule.approval_required,
            )
            self._effects[effect_id] = effect
            self._intent_ids[intent.intent_id] = effect_id
            self._append_transition(
                event_id,
                "effect.intent",
                "agent",
                effect,
                "proposed",
            )
            return self._record(effect)

        return self._apply(event_id, "effect.intent", fingerprint_payload, mutate)

    def request_approval(
        self, event_id: str, effect_id: str, *, approval_ref: str
    ) -> EffectRecord:
        """Require an explicit Host approval before authorizing one effect."""
        reference = _opaque_id(approval_ref, "approval_ref")
        identifier = _opaque_id(effect_id, "effect_id")

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"proposed"})
            if not effect.approval_required:
                raise EffectStateError(
                    "Effect policy does not require an approval transition."
                )
            effect.approval_ref = reference
            self._append_transition(
                event_id,
                "effect.approval_required",
                "host",
                effect,
                "approval_required",
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.approval_required",
            {"effect_id": identifier, "approval_ref": reference},
            mutate,
        )

    def authorize(
        self,
        event_id: str,
        effect_id: str,
        *,
        authorization_ref: str,
        approval_ref: str | None = None,
    ) -> EffectRecord:
        """Record a Host policy decision that permits exactly one effect intent."""
        identifier = _opaque_id(effect_id, "effect_id")
        authorization = _opaque_id(authorization_ref, "authorization_ref")
        approval = (
            _opaque_id(approval_ref, "approval_ref")
            if approval_ref is not None
            else None
        )

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            if effect.approval_required:
                if effect.state != "approval_required":
                    raise EffectStateError(
                        "Effect policy requires approval before authorization."
                    )
                if approval is None or approval != effect.approval_ref:
                    raise EffectStateError(
                        "Authorization requires the matching approval reference."
                    )
            else:
                if effect.state != "proposed":
                    self._require_state(effect, {"proposed"})
                if approval is not None:
                    raise EffectStateError(
                        "Direct authorization cannot attach an unrequested approval."
                    )
            effect.authorization_ref = authorization
            self._append_transition(
                event_id, "effect.authorized", "host", effect, "authorized"
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.authorized",
            {
                "effect_id": identifier,
                "authorization_ref": authorization,
                "approval_ref": approval,
            },
            mutate,
        )

    def deny_approval(
        self,
        event_id: str,
        effect_id: str,
        *,
        approval_ref: str,
        summary: str,
    ) -> EffectRecord:
        """End an approval-required effect without claiming any provider action."""
        identifier = _opaque_id(effect_id, "effect_id")
        approval = _opaque_id(approval_ref, "approval_ref")
        reason = _bounded_text(summary, "Approval denial summary", 1, 400)

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"approval_required"})
            if effect.approval_ref != approval:
                raise EffectStateError(
                    "Approval denial requires the matching approval."
                )
            effect.evidence_ref = approval
            effect.failure_code = "LAP-301"
            effect.failure_summary = reason
            self._append_transition(
                event_id, "effect.approval_denied", "host", effect, "failed"
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.approval_denied",
            {"effect_id": identifier, "approval_ref": approval, "summary": reason},
            mutate,
        )

    def accept(
        self, event_id: str, effect_id: str, *, provider_operation_ref: str
    ) -> EffectRecord:
        """Record provider acknowledgement without treating it as completion."""
        identifier = _opaque_id(effect_id, "effect_id")
        provider_ref = _opaque_id(provider_operation_ref, "provider_operation_ref")

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"authorized"})
            effect.provider_operation_ref = provider_ref
            self._append_transition(
                event_id, "effect.accepted", "host", effect, "accepted"
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.accepted",
            {"effect_id": identifier, "provider_operation_ref": provider_ref},
            mutate,
        )

    def record_settled(
        self, event_id: str, effect_id: str, *, evidence_ref: str
    ) -> EffectRecord:
        """Record a Host-verified final successful business outcome."""
        return self._record_direct_outcome(
            event_id,
            effect_id,
            event_type="effect.settled",
            state="settled",
            evidence_ref=evidence_ref,
            failure_code=None,
            failure_summary=None,
        )

    def record_failed(
        self,
        event_id: str,
        effect_id: str,
        *,
        evidence_ref: str,
        failure_code: str,
        failure_summary: str,
    ) -> EffectRecord:
        """Record a Host-verified failed external outcome without retrying it."""
        return self._record_direct_outcome(
            event_id,
            effect_id,
            event_type="effect.failed",
            state="failed",
            evidence_ref=evidence_ref,
            failure_code=failure_code,
            failure_summary=failure_summary,
        )

    def record_unknown(
        self,
        event_id: str,
        effect_id: str,
        *,
        observation_ref: str,
    ) -> EffectRecord:
        """Record an Agent-observed outcome gap without guessing or retrying."""
        identifier = _opaque_id(effect_id, "effect_id")
        observation = _opaque_id(observation_ref, "observation_ref")

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"authorized", "accepted"})
            effect.evidence_ref = observation
            self._append_transition(
                event_id, "effect.unknown", "host", effect, "unknown"
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.unknown",
            {"effect_id": identifier, "observation_ref": observation},
            mutate,
        )

    def begin_reconciliation(
        self, event_id: str, effect_id: str, *, reconciliation_ref: str
    ) -> EffectRecord:
        """Record the Host's provider-specific reconciliation attempt boundary."""
        identifier = _opaque_id(effect_id, "effect_id")
        reference = _opaque_id(reconciliation_ref, "reconciliation_ref")

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"unknown"})
            effect.evidence_ref = reference
            self._append_transition(
                event_id, "effect.reconciling", "host", effect, "reconciling"
            )
            return self._record(effect)

        return self._apply(
            event_id,
            "effect.reconciling",
            {"effect_id": identifier, "reconciliation_ref": reference},
            mutate,
        )

    def resolve_reconciliation(
        self,
        event_id: str,
        effect_id: str,
        *,
        outcome: str,
        evidence_ref: str,
        failure_code: str | None = None,
        failure_summary: str | None = None,
    ) -> EffectRecord:
        """Finish reconciliation as settled, failed, or indeterminate evidence."""
        if outcome not in _RECONCILIATION_OUTCOMES:
            raise EffectValidationError("Reconciliation outcome is invalid.")
        identifier = _opaque_id(effect_id, "effect_id")
        evidence = _opaque_id(evidence_ref, "evidence_ref")
        code, summary = _failure_details(outcome, failure_code, failure_summary)

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"reconciling"})
            effect.evidence_ref = evidence
            effect.failure_code = code
            effect.failure_summary = summary
            self._append_transition(
                event_id, f"effect.{outcome}", "host", effect, outcome
            )
            return self._record(effect)

        return self._apply(
            event_id,
            f"effect.{outcome}",
            {
                "effect_id": identifier,
                "outcome": outcome,
                "evidence_ref": evidence,
                "failure_code": code,
                "failure_summary": summary,
            },
            mutate,
        )

    def record(self, effect_id: str) -> EffectRecord:
        """Return one current immutable effect record from this Host scope."""
        identifier = _opaque_id(effect_id, "effect_id")
        with self._lock:
            return self._record(self._effect(identifier))

    def records(self) -> tuple[EffectRecord, ...]:
        """Return current immutable records in first-intent order."""
        with self._lock:
            return tuple(self._record(effect) for effect in self._effects.values())

    def transitions(self) -> tuple[EffectTransition, ...]:
        """Return immutable accepted lifecycle transitions in append order."""
        with self._lock:
            return tuple(self._transitions)

    def anomalies(self) -> tuple[EffectAnomaly, ...]:
        """Return late terminal attempts retained without changing effect history."""
        with self._lock:
            return tuple(self._anomalies)

    def snapshot(self) -> EffectSnapshot:
        """Return safe scoped counts for Host recovery and operator diagnostics."""
        with self._lock:
            unresolved = sum(
                effect.required and effect.state != "settled"
                for effect in self._effects.values()
            )
            return EffectSnapshot(
                scope=self._scope,
                capability_id=self._capability_id,
                effect_count=len(self._effects),
                transition_count=len(self._transitions),
                anomaly_count=len(self._anomalies),
                unresolved_required_count=unresolved,
            )

    def validate_success(self) -> tuple[EffectRecord, ...]:
        """Require every Host-required effect to have verified settlement first."""
        with self._lock:
            required = tuple(
                self._record(effect)
                for effect in self._effects.values()
                if effect.required
            )
            if any(effect.state != "settled" for effect in required):
                raise EffectTerminalGateError()
            return required

    def _record_direct_outcome(
        self,
        event_id: str,
        effect_id: str,
        *,
        event_type: str,
        state: str,
        evidence_ref: str,
        failure_code: str | None,
        failure_summary: str | None,
    ) -> EffectRecord:
        """Apply one Host-verified settled or failed outcome after acceptance."""
        identifier = _opaque_id(effect_id, "effect_id")
        evidence = _opaque_id(evidence_ref, "evidence_ref")
        code, summary = _failure_details(state, failure_code, failure_summary)

        def mutate() -> EffectRecord:
            effect = self._effect(identifier)
            self._require_state(effect, {"accepted"})
            effect.evidence_ref = evidence
            effect.failure_code = code
            effect.failure_summary = summary
            self._append_transition(event_id, event_type, "host", effect, state)
            return self._record(effect)

        return self._apply(
            event_id,
            event_type,
            {
                "effect_id": identifier,
                "evidence_ref": evidence,
                "failure_code": code,
                "failure_summary": summary,
            },
            mutate,
        )

    def _apply(
        self,
        event_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        mutate: Callable[[], _Outcome],
    ) -> _Outcome:
        """Apply one idempotent event or retain one late terminal anomaly."""
        identifier = _opaque_id(event_id, "event_id")
        fingerprint = _event_fingerprint(event_type, payload)
        with self._lock:
            existing = self._events.get(identifier)
            if existing is not None:
                if (
                    existing.event_type != event_type
                    or existing.fingerprint != fingerprint
                ):
                    raise EffectConflictError(
                        "Event ID is already bound to different effect data."
                    )
                return cast(_Outcome, existing.outcome)
            rejected = self._rejected_events.get(identifier)
            if rejected is not None:
                if (
                    rejected.event_type != event_type
                    or rejected.fingerprint != fingerprint
                ):
                    raise EffectConflictError(
                        "Event ID is already bound to a different rejected effect event."
                    )
                raise EffectTerminalConflictError(
                    rejected.anomaly.effect_id, rejected.anomaly.observed_state
                )
            try:
                outcome = mutate()
            except EffectTerminalConflictError as exc:
                anomaly = EffectAnomaly(
                    event_id=identifier,
                    event_type=event_type,
                    effect_id=exc.effect_id,
                    observed_state=exc.observed_state,
                    reason="terminal_effect_record_already_exists",
                    recorded_at=_timestamp(),
                )
                self._rejected_events[identifier] = _RejectedEvent(
                    event_type=event_type,
                    fingerprint=fingerprint,
                    anomaly=anomaly,
                )
                self._anomalies.append(anomaly)
                raise
            if not isinstance(outcome, EffectRecord):
                raise EffectValidationError("Effect event produced an invalid outcome.")
            self._events[identifier] = _EventRecord(event_type, fingerprint, outcome)
            return cast(_Outcome, outcome)

    def _effect(self, effect_id: str) -> _EffectState:
        """Resolve one effect in this ledger without exposing cross-scope state."""
        effect = self._effects.get(effect_id)
        if effect is None:
            raise EffectValidationError("Effect record is unknown in this Run scope.")
        return effect

    def _require_state(self, effect: _EffectState, allowed: set[str]) -> None:
        """Require an active allowed state while retaining late terminal evidence."""
        if effect.state in _TERMINAL_STATES:
            raise EffectTerminalConflictError(effect.effect_id, effect.state)
        if effect.state not in allowed:
            raise EffectStateError("Effect event is not legal from its current state.")

    def _append_transition(
        self,
        event_id: str,
        event_type: str,
        actor: str,
        effect: _EffectState,
        next_state: str,
    ) -> None:
        """Append one Host-applied transition and advance the private effect state."""
        prior_state = effect.state
        effect.state = next_state
        self._transitions.append(
            EffectTransition(
                event_id=_opaque_id(event_id, "event_id"),
                event_type=event_type,
                actor=actor,
                effect_id=effect.effect_id,
                prior_state=prior_state,
                state=next_state,
                recorded_at=_timestamp(),
            )
        )

    def _record(self, effect: _EffectState) -> EffectRecord:
        """Build one immutable Host record snapshot from private mutable state."""
        return EffectRecord(
            effect_id=effect.effect_id,
            scope=self._scope,
            capability_id=self._capability_id,
            intent=effect.intent,
            required=effect.required,
            approval_required=effect.approval_required,
            state=effect.state,
            authorization_ref=effect.authorization_ref,
            approval_ref=effect.approval_ref,
            provider_operation_ref=effect.provider_operation_ref,
            evidence_ref=effect.evidence_ref,
            failure_code=effect.failure_code,
            failure_summary=effect.failure_summary,
        )

    def _new_effect_id(self) -> str:
        """Generate a collision-free opaque Host-owned effect identifier."""
        while True:
            effect_id = f"effect-{secrets.token_urlsafe(18)}"
            if effect_id not in self._effects:
                return effect_id


def _allowed_keys(
    value: Mapping[str, Any], allowed: set[str], required: set[str], label: str
) -> None:
    """Require exactly the known required fields without hidden extension data."""
    if not required <= set(value) or not set(value) <= allowed:
        raise EffectValidationError(f"{label} has missing or unsupported fields.")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    """Require one JSON-object-shaped value with only string keys."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise EffectValidationError(f"{label} must be a JSON object.")
    return cast(Mapping[str, Any], value)


def _opaque_id(value: Any, label: str) -> str:
    """Validate one bounded valid-UTF-8 Host or Agent opaque identifier."""
    if not isinstance(value, str) or not value:
        raise EffectValidationError(f"{label} must be a non-empty string.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EffectValidationError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise EffectValidationError(f"{label} must be at most 240 bytes.")
    return value


def _bounded_text(value: Any, label: str, minimum: int, maximum: int) -> str:
    """Validate one bounded valid-UTF-8 text field."""
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise EffectValidationError(f"{label} is invalid.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EffectValidationError(f"{label} must be valid UTF-8 text.") from exc
    return value


def _effect_type(value: Any) -> str:
    """Validate one stable profile effect-type identifier."""
    if not isinstance(value, str) or not _EFFECT_TYPE_RE.fullmatch(value):
        raise EffectValidationError("Effect type is invalid.")
    return value


def _effect_types(values: Iterable[str]) -> tuple[str, ...]:
    """Validate a non-empty, deterministic immutable Host effect allow-list."""
    if isinstance(values, (str, bytes)):
        raise EffectValidationError("Effect allow-list must be an iterable of types.")
    try:
        items = tuple(_effect_type(value) for value in values)
    except TypeError as exc:
        raise EffectValidationError("Effect allow-list must be iterable.") from exc
    if not items or len(items) != len(set(items)):
        raise EffectValidationError("Effect allow-list must be non-empty and unique.")
    return tuple(sorted(items, key=lambda value: value.encode("utf-8")))


def _effect_rules(values: Iterable[EffectRule]) -> dict[str, EffectRule]:
    """Validate and freeze one deterministic Host effect-rule map."""
    if isinstance(values, (str, bytes)):
        raise EffectValidationError("Effect rules must be an iterable of rules.")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise EffectValidationError("Effect rules must be iterable.") from exc
    if not items or any(not isinstance(item, EffectRule) for item in items):
        raise EffectValidationError("Effect rules must be non-empty EffectRule values.")
    if len({item.effect_type for item in items}) != len(items):
        raise EffectValidationError("Effect rules must have unique effect types.")
    return {
        item.effect_type: item
        for item in sorted(items, key=lambda rule: rule.effect_type.encode("utf-8"))
    }


def _digest(value: Any, label: str) -> str:
    """Validate one lowercase SHA-256 digest with its explicit Core scheme."""
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise EffectValidationError(f"{label} must be a sha256 digest.")
    return value


def _failure_details(
    outcome: str,
    failure_code: str | None,
    failure_summary: str | None,
) -> tuple[str | None, str | None]:
    """Require safe failure facts only when an effect cannot be settled."""
    if outcome == "settled":
        if failure_code is not None or failure_summary is not None:
            raise EffectValidationError("A settled effect cannot contain failure data.")
        return None, None
    if (
        not isinstance(failure_code, str)
        or not _ERROR_CODE_RE.fullmatch(failure_code)
        or failure_summary is None
    ):
        raise EffectValidationError("An unresolved effect requires safe failure data.")
    return failure_code, _bounded_text(failure_summary, "Failure summary", 1, 400)


def _event_fingerprint(event_type: str, payload: Mapping[str, Any]) -> str:
    """Build a deterministic local duplicate-comparison identity for one event."""
    serialized = _json_object(payload, "Effect event")
    digest = hashlib.sha256()
    digest.update(_EVENT_DOMAIN)
    digest.update(event_type.encode("utf-8"))
    digest.update(b"\n")
    digest.update(serialized.encode("utf-8"))
    return digest.hexdigest()


def _json_object(value: Mapping[str, Any], label: str) -> str:
    """Serialize one finite valid-UTF-8 JSON object for local comparison only."""
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        serialized.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EffectValidationError(
            f"{label} must be valid finite UTF-8 JSON."
        ) from exc
    return serialized


def _timestamp() -> str:
    """Return one UTC RFC 3339 timestamp for a reference-ledger record."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
