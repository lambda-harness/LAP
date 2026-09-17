"""Reference Core 0.2 Artifact offer, receipt, and success-gating semantics.

The ledger validates portable Artifact metadata and byte identity, but it does
not implement an object store, a download URL, malware scanning, or a durable
database. A Host must atomically persist its copied bytes, receipt record, and
terminal Run transition before it exposes the receipt or reports success.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

_DELIVERY_KINDS: Final = frozenset(("download", "reference", "inline"))
_DELIVERY_SCOPES: Final = frozenset(("run", "session", "tenant"))
_SEMANTIC_ROLES: Final = frozenset(
    ("intermediate", "preview", "final_result", "error_report")
)
_SHA256_RE: Final = re.compile(r"^[a-f0-9]{64}$")
_MEDIA_TYPE_RE: Final = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
)
_SOURCE_REF_RE: Final = re.compile(
    r"^(?:lap://|urn:)[A-Za-z0-9][A-Za-z0-9._~:/-]{0,1023}$"
)


class ArtifactLedgerError(ValueError):
    """Represent one safe, typed Artifact lifecycle rejection.

    Args:
        code: Stable LAP error code used by the present Core 0.2 draft.
        message: Display-safe explanation with no private path or byte content.
    """

    def __init__(self, code: str, message: str) -> None:
        """Initialize a typed Artifact lifecycle error."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ArtifactValidationError(ArtifactLedgerError):
    """Reject malformed metadata or an unknown Artifact lifecycle reference."""

    def __init__(self, message: str) -> None:
        """Initialize a safe Artifact validation rejection."""
        super().__init__("LAP-201", message)


class ArtifactPolicyError(ArtifactLedgerError):
    """Reject a delivery or media policy the Host did not admit."""

    def __init__(self, message: str) -> None:
        """Initialize a safe Artifact policy rejection."""
        super().__init__("LAP-402", message)


class ArtifactQuotaError(ArtifactLedgerError):
    """Reject an Artifact that exceeds a Host-reserved capacity bound."""

    def __init__(self, message: str) -> None:
        """Initialize a safe Artifact quota rejection."""
        super().__init__("LAP-401", message)


class ArtifactIntegrityError(ArtifactLedgerError):
    """Reject bytes that do not match their accepted Offer identity."""

    def __init__(self, message: str) -> None:
        """Initialize a safe Artifact integrity rejection."""
        super().__init__("LAP-201", message)


class ArtifactConflictError(ArtifactLedgerError):
    """Reject a reused Artifact ID with a different immutable identity."""

    def __init__(self, message: str) -> None:
        """Initialize the Core 0.2 Artifact identity-conflict rejection."""
        super().__init__("LAP-109", message)


class ArtifactTerminalError(ArtifactLedgerError):
    """Reject success when its declared Artifact receipt set is incomplete."""

    def __init__(self, message: str) -> None:
        """Initialize a safe terminal Artifact-gating rejection."""
        super().__init__("LAP-201", message)


@dataclass(frozen=True)
class ArtifactScope:
    """Host-issued tenant and Run scope attached to every committed receipt."""

    tenant_id: str
    run_id: str

    def __post_init__(self) -> None:
        """Validate opaque scope identifiers before a ledger accepts them."""
        object.__setattr__(self, "tenant_id", _opaque_id(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "run_id", _opaque_id(self.run_id, "run_id"))

    def payload(self) -> dict[str, str]:
        """Return the Core receipt scope representation."""
        return {"tenant_id": self.tenant_id, "run_id": self.run_id}


@dataclass(frozen=True)
class ArtifactOffer:
    """Immutable Agent-proposed metadata after Host-side structural validation."""

    artifact_id: str
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    source_ref: str
    delivery_json: str
    semantic_json: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ArtifactOffer:
        """Parse one schema-shaped Core Artifact Offer without ambient paths."""
        value = _object(payload, "Artifact offer")
        _exact_keys(
            value,
            {
                "artifact_id",
                "name",
                "media_type",
                "size_bytes",
                "sha256",
                "source_ref",
                "delivery",
                "semantic",
            },
            "Artifact offer",
        )
        artifact_id = _opaque_id(value["artifact_id"], "artifact_id")
        name = _artifact_name(value["name"])
        media_type = _media_type(value["media_type"])
        size_bytes = _nonnegative_int(value["size_bytes"], "size_bytes")
        sha256 = _sha256(value["sha256"])
        source_ref = _source_ref(value["source_ref"])
        delivery_json = _delivery_json(value["delivery"])
        semantic_json = _semantic_json(value["semantic"])
        return cls(
            artifact_id=artifact_id,
            name=name,
            media_type=media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            source_ref=source_ref,
            delivery_json=delivery_json,
            semantic_json=semantic_json,
        )

    @property
    def delivery(self) -> dict[str, Any]:
        """Return a defensive copy of the delivery policy."""
        return _decode_object(self.delivery_json)

    @property
    def semantic(self) -> dict[str, Any]:
        """Return a defensive copy of the semantic display metadata."""
        return _decode_object(self.semantic_json)

    @property
    def required(self) -> bool:
        """Return whether success must include this Artifact receipt."""
        return cast(bool, self.delivery["required"])

    def payload(self) -> dict[str, Any]:
        """Return a safe Core Artifact Offer payload copy."""
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "source_ref": self.source_ref,
            "delivery": self.delivery,
            "semantic": self.semantic,
        }


@dataclass(frozen=True)
class ArtifactReceipt:
    """Host-issued immutable identity for a successfully materialized Artifact."""

    artifact_id: str
    receipt_id: str
    canonical_ref: str
    sha256: str
    size_bytes: int
    scope: ArtifactScope

    def payload(self) -> dict[str, Any]:
        """Return the Core Artifact receipt payload without byte-store details."""
        return {
            "artifact_id": self.artifact_id,
            "receipt_id": self.receipt_id,
            "canonical_ref": self.canonical_ref,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "scope": self.scope.payload(),
        }


class ArtifactLedger:
    """Apply Artifact Offer/commit identity rules for one Host-issued Run scope.

    The Host owns the scope and policy. The Agent supplies only a proposed
    Offer and the exact bytes behind its declared source reference. This object
    does not retain bytes and therefore cannot create a user-facing download
    link; a production Host must pair it with scoped durable object storage.
    """

    def __init__(
        self,
        scope: ArtifactScope,
        *,
        max_artifacts: int = 64,
        max_artifact_bytes: int = 1024 * 1024 * 1024,
        allowed_media_types: Collection[str] | None = None,
        supported_delivery_kinds: Collection[str] = _DELIVERY_KINDS,
        supported_delivery_scopes: Collection[str] = _DELIVERY_SCOPES,
    ) -> None:
        """Create a scope-bound reference ledger with explicit Host policy.

        Args:
            scope: Authenticated Host scope, never Agent-provided input.
            max_artifacts: Maximum distinct Artifact IDs admitted for the Run.
            max_artifact_bytes: Per-Artifact byte ceiling reserved by the Host.
            allowed_media_types: Optional exact MIME allow-list.
            supported_delivery_kinds: Delivery kinds the Host can materialize.
            supported_delivery_scopes: Retention/isolation scopes the Host permits.
        """
        if not isinstance(scope, ArtifactScope):
            raise ArtifactValidationError("Artifact scope must be Host-issued.")
        self._scope = scope
        self._max_artifacts = _positive_int(max_artifacts, "max_artifacts")
        self._max_artifact_bytes = _nonnegative_int(
            max_artifact_bytes, "max_artifact_bytes"
        )
        self._allowed_media_types = (
            None
            if allowed_media_types is None
            else _policy_values(allowed_media_types, "allowed_media_types")
        )
        self._supported_delivery_kinds = _policy_values(
            supported_delivery_kinds, "supported_delivery_kinds"
        )
        self._supported_delivery_scopes = _policy_values(
            supported_delivery_scopes, "supported_delivery_scopes"
        )
        self._offers: dict[str, ArtifactOffer] = {}
        self._receipts_by_artifact: dict[str, ArtifactReceipt] = {}
        self._receipts_by_id: dict[str, ArtifactReceipt] = {}
        self._lock = threading.RLock()

    @property
    def scope(self) -> ArtifactScope:
        """Return the immutable Host-issued scope for this ledger."""
        return self._scope

    def offer(self, payload: Mapping[str, Any]) -> ArtifactOffer:
        """Admit one immutable Offer or return its prior idempotent record."""
        offer = ArtifactOffer.from_payload(payload)
        with self._lock:
            existing = self._offers.get(offer.artifact_id)
            if existing is not None:
                if existing != offer:
                    raise ArtifactConflictError(
                        "Artifact ID was reused with different immutable metadata."
                    )
                return existing
            if len(self._offers) >= self._max_artifacts:
                raise ArtifactQuotaError("Artifact count exceeds the Host reservation.")
            if offer.size_bytes > self._max_artifact_bytes:
                raise ArtifactQuotaError("Artifact size exceeds the Host reservation.")
            self._validate_policy(offer)
            self._offers[offer.artifact_id] = offer
            return offer

    def commit(self, artifact_id: str, content: bytes) -> ArtifactReceipt:
        """Validate exact bytes and issue one idempotent opaque Host receipt."""
        selected_id = _opaque_id(artifact_id, "artifact_id")
        if not isinstance(content, bytes):
            raise ArtifactValidationError("Artifact content must be bytes.")
        with self._lock:
            try:
                offer = self._offers[selected_id]
            except KeyError as exc:
                raise ArtifactValidationError(
                    "Artifact must be offered before it can be committed."
                ) from exc
            self._validate_content(offer, content)
            existing = self._receipts_by_artifact.get(selected_id)
            if existing is not None:
                return existing
            receipt_id = f"receipt-{secrets.token_urlsafe(18)}"
            receipt = ArtifactReceipt(
                artifact_id=offer.artifact_id,
                receipt_id=receipt_id,
                canonical_ref=f"lap://artifact/{receipt_id}",
                sha256=offer.sha256,
                size_bytes=offer.size_bytes,
                scope=self._scope,
            )
            self._receipts_by_artifact[selected_id] = receipt
            self._receipts_by_id[receipt.receipt_id] = receipt
            return receipt

    def receipt_for(self, artifact_id: str) -> ArtifactReceipt | None:
        """Return a committed receipt by Artifact ID without exposing bytes."""
        selected_id = _opaque_id(artifact_id, "artifact_id")
        with self._lock:
            return self._receipts_by_artifact.get(selected_id)

    def validate_success(
        self, receipt_ids: Collection[str]
    ) -> tuple[ArtifactReceipt, ...]:
        """Require every offered required Artifact receipt in a success proposal.

        The method intentionally accepts receipt IDs only. Passing Artifact
        metadata again is not an alternate success path and remains prohibited
        by the Core 0.2 `run.result` contract.
        """
        with self._lock:
            selected = self._validated_receipts(receipt_ids)
            required_ids = {
                offer.artifact_id for offer in self._offers.values() if offer.required
            }
            committed_ids = {receipt.artifact_id for receipt in selected}
            if required_ids - committed_ids:
                raise ArtifactTerminalError(
                    "Success is missing one or more required Artifact receipts."
                )
            return selected

    def validate_receipts(
        self, receipt_ids: Collection[str]
    ) -> tuple[ArtifactReceipt, ...]:
        """Validate scoped receipt references without imposing a success gate.

        Failed, cancelled, and indeterminate results may still reference a
        committed preview or error-report Artifact. They must receive the same
        opaque-ID, duplicate, existence, and Run-scope validation as a success
        proposal, but they do not need to include every required deliverable.
        """
        with self._lock:
            return self._validated_receipts(receipt_ids)

    def _validate_policy(self, offer: ArtifactOffer) -> None:
        if (
            self._allowed_media_types is not None
            and offer.media_type not in self._allowed_media_types
        ):
            raise ArtifactPolicyError("Artifact media type is not allowed by the Host.")
        delivery = offer.delivery
        # ArtifactOffer.from_payload has already validated these fields.
        kind = cast(str, delivery["kind"])
        scope = cast(str, delivery["scope"])
        if kind not in self._supported_delivery_kinds:
            raise ArtifactPolicyError(
                "Artifact delivery kind is not supported by the Host."
            )
        if scope not in self._supported_delivery_scopes:
            raise ArtifactPolicyError(
                "Artifact delivery scope is not allowed by the Host."
            )

    def _validate_content(self, offer: ArtifactOffer, content: bytes) -> None:
        if len(content) != offer.size_bytes:
            raise ArtifactIntegrityError(
                "Artifact bytes do not match the offered size."
            )
        if hashlib.sha256(content).hexdigest() != offer.sha256:
            raise ArtifactIntegrityError(
                "Artifact bytes do not match the offered digest."
            )

    def _validated_receipts(
        self, receipt_ids: Collection[str]
    ) -> tuple[ArtifactReceipt, ...]:
        """Return known scope-bound receipts while the ledger lock is held."""
        if isinstance(receipt_ids, str) or not isinstance(receipt_ids, Collection):
            raise ArtifactTerminalError("Result must contain a receipt ID collection.")
        selected: list[ArtifactReceipt] = []
        seen: set[str] = set()
        for receipt_id in receipt_ids:
            identifier = _opaque_id(receipt_id, "receipt_id")
            if identifier in seen:
                raise ArtifactTerminalError("Result cannot repeat an Artifact receipt.")
            seen.add(identifier)
            try:
                receipt = self._receipts_by_id[identifier]
            except KeyError as exc:
                raise ArtifactTerminalError(
                    "Result references an uncommitted Artifact receipt."
                ) from exc
            if receipt.scope != self._scope:
                raise ArtifactTerminalError(
                    "Artifact receipt is outside the Run scope."
                )
            selected.append(receipt)
        return tuple(selected)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ArtifactValidationError(f"{label} must be a JSON object.")
    return cast(Mapping[str, Any], value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ArtifactValidationError(f"{label} has missing or unsupported fields.")


def _opaque_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{label} must be a non-empty string.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ArtifactValidationError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise ArtifactValidationError(f"{label} must be at most 240 bytes.")
    return value


def _artifact_name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError("Artifact name must be non-empty bounded text.")
    try:
        if len(value.encode("utf-8")) > 240:
            raise ArtifactValidationError(
                "Artifact name must be non-empty bounded text."
            )
    except UnicodeEncodeError as exc:
        raise ArtifactValidationError(
            "Artifact name must be valid UTF-8 text."
        ) from exc
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise ArtifactValidationError("Artifact name must not contain a path.")
    return value


def _media_type(value: Any) -> str:
    if not isinstance(value, str) or not _MEDIA_TYPE_RE.fullmatch(value):
        raise ArtifactValidationError(
            "Artifact media type must be a lowercase MIME type."
        )
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArtifactValidationError(f"{label} must be a non-negative integer.")
    return cast(int, value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ArtifactValidationError(f"{label} must be a positive integer.")
    return cast(int, value)


def _sha256(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ArtifactValidationError("Artifact sha256 must be lowercase hexadecimal.")
    return value


def _source_ref(value: Any) -> str:
    if not isinstance(value, str) or not _SOURCE_REF_RE.fullmatch(value):
        raise ArtifactValidationError(
            "Artifact source_ref must be a LAP or URN reference."
        )
    return value


def _delivery_json(value: Any) -> str:
    delivery = _object(value, "Artifact delivery")
    _exact_keys(
        delivery,
        {"kind", "required", "disposition", "scope", "retention"},
        "Artifact delivery",
    )
    kind = delivery["kind"]
    disposition = delivery["disposition"]
    scope = delivery["scope"]
    if not isinstance(kind, str) or kind not in _DELIVERY_KINDS:
        raise ArtifactValidationError("Artifact delivery kind is invalid.")
    if not isinstance(delivery["required"], bool):
        raise ArtifactValidationError("Artifact delivery required must be boolean.")
    if not isinstance(disposition, str) or disposition not in {"attachment", "inline"}:
        raise ArtifactValidationError("Artifact delivery disposition is invalid.")
    if kind == "download" and disposition != "attachment":
        raise ArtifactValidationError(
            "Download delivery must use attachment disposition."
        )
    if kind == "inline" and disposition != "inline":
        raise ArtifactValidationError("Inline delivery must use inline disposition.")
    if not isinstance(scope, str) or scope not in _DELIVERY_SCOPES:
        raise ArtifactValidationError("Artifact delivery scope is invalid.")
    retention = _object(delivery["retention"], "Artifact retention")
    if set(retention) - {"class", "expires_at"} or "class" not in retention:
        raise ArtifactValidationError("Artifact retention fields are invalid.")
    if not isinstance(retention["class"], str) or not retention["class"]:
        raise ArtifactValidationError("Artifact retention class is invalid.")
    if "expires_at" in retention and (
        not isinstance(retention["expires_at"], str) or not retention["expires_at"]
    ):
        raise ArtifactValidationError("Artifact retention expiry is invalid.")
    return _json_object(delivery, "Artifact delivery")


def _semantic_json(value: Any) -> str:
    semantic = _object(value, "Artifact semantic")
    if (
        set(semantic) - {"role", "title", "description", "source_count"}
        or "role" not in semantic
    ):
        raise ArtifactValidationError("Artifact semantic fields are invalid.")
    role = semantic["role"]
    if not isinstance(role, str) or role not in _SEMANTIC_ROLES:
        raise ArtifactValidationError("Artifact semantic role is invalid.")
    for field, maximum in (("title", 400), ("description", 400)):
        if field in semantic and (
            not isinstance(semantic[field], str)
            or not semantic[field]
            or len(semantic[field]) > maximum
        ):
            raise ArtifactValidationError(f"Artifact semantic {field} is invalid.")
    if "source_count" in semantic:
        _nonnegative_int(semantic["source_count"], "source_count")
    return _json_object(semantic, "Artifact semantic")


def _json_object(value: Mapping[str, Any], label: str) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError(
            f"{label} must contain finite JSON values."
        ) from exc
    if not isinstance(decoded, dict):
        raise ArtifactValidationError(f"{label} must be a JSON object.")
    return encoded


def _decode_object(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    assert isinstance(decoded, dict)
    return decoded


def _policy_values(values: Collection[str], label: str) -> frozenset[str]:
    """Normalize one required Host policy collection without ambient defaults."""
    if isinstance(values, str) or not isinstance(values, Collection):
        raise ArtifactValidationError(f"{label} must be a string collection.")
    normalized_items: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ArtifactValidationError(f"{label} must contain non-empty strings.")
        normalized_items.append(value)
    normalized = frozenset(normalized_items)
    if not normalized:
        raise ArtifactValidationError(f"{label} must contain non-empty strings.")
    return normalized
