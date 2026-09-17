"""Reference Core 0.2 release-identity and pre-context activation semantics.

The gate compares the exact Host-admitted release identity with the running
Agent identity before it invokes a context supplier. It validates and compares
already computed digests; it does not implement RFC 8785, package hashing,
signature trust, peer authentication, or a durable release registry.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_Context = TypeVar("_Context")


class ContractGateError(ValueError):
    """Represent one safe Core release-contract activation rejection."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize the rejection with a stable LAP code and safe message."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ContractValidationError(ContractGateError):
    """Reject malformed release identity metadata before activation comparison."""

    def __init__(self, message: str) -> None:
        """Initialize the release metadata validation rejection."""
        super().__init__("LAP-201", message)


class ContractMismatchError(ContractGateError):
    """Reject a running Agent that differs from the admitted release identity."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        """Initialize the activation mismatch without exposing business context."""
        self.fields = fields
        super().__init__(
            "LAP-103", "Running release identity does not match the admitted release."
        )


@dataclass(frozen=True)
class ReleaseIdentity:
    """Immutable Core release identity used for negotiation and Run admission."""

    agent_id: str
    version: str
    package_digest: str
    manifest_digest: str
    capability_digests: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Defend the public value object against direct invalid construction."""
        _opaque_id(self.agent_id, "agent_id")
        _bounded_text(self.version, "version", 1, 120)
        _digest(self.package_digest, "package_digest")
        _digest(self.manifest_digest, "manifest_digest")
        _validate_capability_pairs(self.capability_digests)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReleaseIdentity:
        """Parse one schema-shaped Core 0.2 release object."""
        value = _object(payload, "Release identity")
        expected = {
            "agent_id",
            "version",
            "package_digest",
            "manifest_digest",
            "capability_contracts",
        }
        if set(value) != expected:
            raise ContractValidationError(
                "Release identity has missing or unsupported fields."
            )
        agent_id = _opaque_id(value["agent_id"], "agent_id")
        version = _bounded_text(value["version"], "version", 1, 120)
        package_digest = _digest(value["package_digest"], "package_digest")
        manifest_digest = _digest(value["manifest_digest"], "manifest_digest")
        capabilities = _capability_digests(value["capability_contracts"])
        return cls(
            agent_id=agent_id,
            version=version,
            package_digest=package_digest,
            manifest_digest=manifest_digest,
            capability_digests=capabilities,
        )

    @property
    def capability_contracts(self) -> dict[str, str]:
        """Return a defensive mapping of declared capability contract digests."""
        return dict(self.capability_digests)

    def payload(self) -> dict[str, Any]:
        """Return a schema-shaped defensive release identity copy."""
        return {
            "agent_id": self.agent_id,
            "version": self.version,
            "package_digest": self.package_digest,
            "manifest_digest": self.manifest_digest,
            "capability_contracts": self.capability_contracts,
        }


@dataclass(frozen=True)
class ActivationAdmission:
    """Describe a successful exact release comparison before context delivery."""

    release: ReleaseIdentity


class ContractGate:
    """Fence business context behind one exact Host-admitted release identity.

    A production Host must obtain ``expected_release`` from its immutable,
    authenticated registry record, authenticate the Agent transport, and
    persist activation decisions. This reference only proves that a context
    supplier is not called until every declared identity component matches.
    """

    def __init__(self, expected_release: ReleaseIdentity) -> None:
        """Create a gate for one immutable Host-admitted release identity."""
        if not isinstance(expected_release, ReleaseIdentity):
            raise ContractValidationError("Expected release must be Host-admitted.")
        self._expected_release = expected_release

    @property
    def expected_release(self) -> ReleaseIdentity:
        """Return the immutable Host-admitted release identity."""
        return self._expected_release

    def verify(
        self, running_release: Mapping[str, Any] | ReleaseIdentity
    ) -> ActivationAdmission:
        """Compare one running identity and reject any release/contract mismatch."""
        actual = _release_identity(running_release, "Running release")
        mismatches = _mismatch_fields(self._expected_release, actual)
        if mismatches:
            raise ContractMismatchError(mismatches)
        return ActivationAdmission(release=actual)

    def admit(
        self,
        running_release: Mapping[str, Any] | ReleaseIdentity,
        context_supplier: Callable[[], _Context],
    ) -> tuple[ActivationAdmission, _Context]:
        """Verify identity before requesting any business context or credential.

        The supplier pattern deliberately prevents a caller from constructing
        or disclosing context until the Host has verified the running release.
        The returned context remains owned by the Host transport and is not
        retained by this reference object.
        """
        if not callable(context_supplier):
            raise ContractValidationError("Context supplier must be callable.")
        admission = self.verify(running_release)
        return admission, context_supplier()


def _release_identity(
    value: Mapping[str, Any] | ReleaseIdentity, label: str
) -> ReleaseIdentity:
    """Normalize one release object while preserving its strict Core shape."""
    if isinstance(value, ReleaseIdentity):
        return value
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be a release identity object.")
    return ReleaseIdentity.from_payload(value)


def _mismatch_fields(
    expected: ReleaseIdentity, actual: ReleaseIdentity
) -> tuple[str, ...]:
    """Return deterministic release components that do not match exactly."""
    fields: list[str] = []
    if expected.agent_id != actual.agent_id:
        fields.append("agent_id")
    if expected.version != actual.version:
        fields.append("version")
    if expected.package_digest != actual.package_digest:
        fields.append("package_digest")
    if expected.manifest_digest != actual.manifest_digest:
        fields.append("manifest_digest")
    if expected.capability_digests != actual.capability_digests:
        fields.append("capability_contracts")
    return tuple(fields)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    """Require one JSON-object-shaped value with only string keys."""
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ContractValidationError(f"{label} must be a JSON object.")
    return cast(Mapping[str, Any], value)


def _opaque_id(value: Any, label: str) -> str:
    """Validate one bounded valid-UTF-8 Core opaque identifier."""
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a non-empty string.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractValidationError(f"{label} must be valid UTF-8 text.") from exc
    if len(encoded) > 240:
        raise ContractValidationError(f"{label} must be at most 240 bytes.")
    return value


def _bounded_text(value: Any, label: str, minimum: int, maximum: int) -> str:
    """Validate one UTF-8 Core text field using Schema character limits."""
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ContractValidationError(f"{label} is invalid.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractValidationError(f"{label} must be valid UTF-8 text.") from exc
    return value


def _digest(value: Any, label: str) -> str:
    """Validate one lowercase SHA-256 digest with its explicit Core scheme."""
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ContractValidationError(f"{label} must be a sha256 digest.")
    return value


def _capability_digests(value: Any) -> tuple[tuple[str, str], ...]:
    """Validate, canonicalize, and defensively retain capability digest pairs."""
    capabilities = _object(value, "capability_contracts")
    if not capabilities:
        raise ContractValidationError("capability_contracts must not be empty.")
    pairs = [
        (_opaque_id(capability_id, "capability_id"), _digest(digest, "contract_digest"))
        for capability_id, digest in capabilities.items()
    ]
    return tuple(sorted(pairs, key=lambda item: item[0].encode("utf-8")))


def _validate_capability_pairs(value: tuple[tuple[str, str], ...]) -> None:
    """Require a non-empty, unique, canonical capability digest tuple."""
    if not isinstance(value, tuple) or not value:
        raise ContractValidationError("capability_digests must be a non-empty tuple.")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in value:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ContractValidationError(
                "capability_digests must contain capability and digest pairs."
            )
        capability_id = _opaque_id(pair[0], "capability_id")
        digest = _digest(pair[1], "contract_digest")
        if capability_id in seen:
            raise ContractValidationError(
                "capability_digests must not repeat a capability."
            )
        seen.add(capability_id)
        pairs.append((capability_id, digest))
    if tuple(sorted(pairs, key=lambda item: item[0].encode("utf-8"))) != value:
        raise ContractValidationError("capability_digests must use canonical ordering.")
