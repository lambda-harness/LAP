"""Reference helpers for the optional LAP Package Signing Profile.

The package content address deliberately excludes only the root
"lap-signature.json" sidecar. Everything else, including "agent.json", is
hashed byte-for-byte. This module is intentionally small enough to be ported
by independent Host implementations.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


LAP_VERSION = "0.1"
SIGNATURE_PROFILE = "lap-package-signing/0.1"
SIGNATURE_FILE_NAME = "lap-signature.json"
SIGNATURE_ALGORITHM = "ed25519"
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_KEY_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{2,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_SIGNATURE_FILE_BYTES = 16 * 1024


class PackageSigningError(ValueError):
    """A safe, typed package-signing failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PackageSignature:
    key_id: str
    agent_id: str
    version: str
    package_sha256: str
    signature: str
    sidecar_sha256: str
    algorithm: str = SIGNATURE_ALGORITHM

    def public(self) -> dict[str, str]:
        return {
            "profile": SIGNATURE_PROFILE,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "package_sha256": self.package_sha256,
        }


@dataclass(frozen=True)
class PackageSignatureVerification:
    status: str
    signature: PackageSignature | None = None

    def public(self) -> dict[str, str]:
        result = {"status": self.status, "profile": SIGNATURE_PROFILE}
        if self.signature is not None:
            result.update(self.signature.public())
        return result


def _raise(message: str, code: str = "LAP-201") -> None:
    raise PackageSigningError(code, message)


def _strict_package_root(package_root: str | Path) -> Path:
    candidate = Path(package_root)
    if candidate.is_symlink():
        _raise("Agent package root must not be a symbolic link.")
    try:
        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise PackageSigningError("LAP-201", "Agent package directory does not exist or cannot be resolved.") from exc
    if not root.is_dir():
        _raise("Agent package path must be a directory.")
    return root


def package_content_sha256(package_root: str | Path, *, maximum_bytes: int | None = None,
                           maximum_files: int | None = None) -> str:
    """Return the canonical LAP package content address.

    The byte stream begins with the ASCII content-digest domain separator and
    then includes every package directory and regular file in UTF-8
    byte-lexical path order. The root signature sidecar is excluded so it can
    sign this value.
    """
    root = _strict_package_root(package_root)
    digest = hashlib.sha256()
    digest.update(b"LAP-PACKAGE-CONTENT-SHA256-v1\0")
    files = 0
    total_bytes = 0
    entries = sorted(
        root.rglob("*"),
        key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
    )
    for path in entries:
        if path.is_symlink():
            _raise("Agent packages must not contain symbolic links.")
        relative = path.relative_to(root).as_posix()
        relative_bytes = relative.encode("utf-8")
        if path.is_dir():
            digest.update(b"D")
            digest.update(len(relative_bytes).to_bytes(4, "big"))
            digest.update(relative_bytes)
            continue
        try:
            mode = path.stat().st_mode
        except OSError as exc:
            raise PackageSigningError("LAP-201", "Agent package content could not be read.") from exc
        if not stat.S_ISREG(mode):
            _raise("Agent packages must contain only normal files and directories.")
        files += 1
        if maximum_files is not None and files > maximum_files:
            _raise("Agent package contains too many files.")
        try:
            before = path.stat()
        except OSError as exc:
            raise PackageSigningError("LAP-201", "Agent package content could not be read.") from exc
        total_bytes += before.st_size
        if maximum_bytes is not None and total_bytes > maximum_bytes:
            raise PackageSigningError("LAP-401", "External Agent package exceeds the Host unpacked size limit.")
        if relative == SIGNATURE_FILE_NAME:
            continue
        digest.update(b"F")
        digest.update(len(relative_bytes).to_bytes(4, "big"))
        digest.update(relative_bytes)
        digest.update(before.st_size.to_bytes(8, "big"))
        try:
            with path.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    digest.update(block)
        except OSError as exc:
            raise PackageSigningError("LAP-201", "Agent package content could not be read.") from exc
        try:
            after = path.stat()
        except OSError as exc:
            raise PackageSigningError("LAP-201", "Agent package content could not be read.") from exc
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            _raise("Agent package changed while its content digest was being calculated.")
    return digest.hexdigest()


def _base64url_decode(value: str, *, label: str, expected_bytes: int | None = None) -> bytes:
    if not isinstance(value, str) or not _BASE64URL_RE.fullmatch(value):
        _raise(f"{label} must be unpadded base64url.", "LAP-201")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise PackageSigningError("LAP-201", f"{label} must be unpadded base64url.") from exc
    if expected_bytes is not None and len(decoded) != expected_bytes:
        _raise(f"{label} has an invalid byte length.", "LAP-201")
    return decoded


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _signature_message(*, key_id: str, agent_id: str, version: str,
                       package_sha256: str) -> bytes:
    return (
        "LAP-PACKAGE-SIGNATURE/0.1\n"
        f"algorithm={SIGNATURE_ALGORITHM}\n"
        f"key_id={key_id}\n"
        f"agent_id={agent_id}\n"
        f"version={version}\n"
        f"package_sha256={package_sha256}\n"
    ).encode("ascii")


def create_package_signature(*, key_id: str, agent_id: str, version: str,
                             package_sha256: str,
                             private_key: Ed25519PrivateKey) -> PackageSignature:
    """Create a detached sidecar record for an already calculated package digest."""
    if not _KEY_ID_RE.fullmatch(key_id):
        _raise("Package signing key_id is invalid.")
    if not _AGENT_ID_RE.fullmatch(agent_id):
        _raise("Package signing agent_id is invalid.")
    if not _VERSION_RE.fullmatch(version):
        _raise("Package signing version is invalid.")
    if not _SHA256_RE.fullmatch(package_sha256):
        _raise("Package signing package_sha256 must be lowercase SHA-256.")
    if not isinstance(private_key, Ed25519PrivateKey):
        _raise("Package signing private key must be Ed25519.")
    signature = _base64url_encode(private_key.sign(_signature_message(
        key_id=key_id,
        agent_id=agent_id,
        version=version,
        package_sha256=package_sha256,
    )))
    return PackageSignature(
        key_id=key_id,
        agent_id=agent_id,
        version=version,
        package_sha256=package_sha256,
        signature=signature,
        sidecar_sha256="",
    )


def _signature_payload(signature: PackageSignature) -> dict[str, str]:
    return {
        "lap": LAP_VERSION,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": signature.key_id,
        "agent_id": signature.agent_id,
        "version": signature.version,
        "package_sha256": signature.package_sha256,
        "signature": signature.signature,
    }


def write_package_signature(package_root: str | Path, signature: PackageSignature, *,
                            overwrite: bool = False) -> PackageSignature:
    """Write one root sidecar without allowing a second signature source."""
    root = _strict_package_root(package_root)
    target = root / SIGNATURE_FILE_NAME
    if target.is_symlink() or (target.exists() and not target.is_file()):
        _raise("Package signature sidecar must be a regular root file.")
    if target.exists() and not overwrite:
        _raise("Package already has a signature sidecar; use explicit overwrite.")
    payload = json.dumps(_signature_payload(signature), ensure_ascii=False,
                         indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if len(payload) > _MAX_SIGNATURE_FILE_BYTES:
        _raise("Package signature sidecar is too large.")
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(mode="xb", dir=root, prefix=".lap-signature-",
                                         suffix=".tmp", delete=False) as handle:
            temporary_name = handle.name
            handle.write(payload)
        os.replace(temporary_name, target)
    except OSError as exc:
        raise PackageSigningError("LAP-500", "Unable to write package signature sidecar.") from exc
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
    return PackageSignature(
        key_id=signature.key_id,
        agent_id=signature.agent_id,
        version=signature.version,
        package_sha256=signature.package_sha256,
        signature=signature.signature,
        sidecar_sha256=hashlib.sha256(payload).hexdigest(),
    )


def read_package_signature(package_root: str | Path, *, agent_id: str, version: str,
                           package_sha256: str) -> PackageSignature | None:
    """Parse and bind a root sidecar to the resolved package identity."""
    root = _strict_package_root(package_root)
    target = root / SIGNATURE_FILE_NAME
    if not target.exists():
        return None
    if target.is_symlink() or not target.is_file():
        _raise("Package signature sidecar must be a regular root file.")
    try:
        raw_bytes = target.read_bytes()
    except OSError as exc:
        raise PackageSigningError("LAP-201", "Package signature sidecar could not be read.") from exc
    if len(raw_bytes) > _MAX_SIGNATURE_FILE_BYTES:
        _raise("Package signature sidecar is too large.")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageSigningError("LAP-201", "Package signature sidecar must be UTF-8 JSON.") from exc
    expected_fields = {
        "lap", "algorithm", "key_id", "agent_id", "version", "package_sha256", "signature",
    }
    if not isinstance(raw, dict) or set(raw) != expected_fields:
        _raise("Package signature sidecar has an invalid field set.")
    if raw.get("lap") != LAP_VERSION:
        _raise("Package signature sidecar declares an unsupported LAP version.", "LAP-102")
    if raw.get("algorithm") != SIGNATURE_ALGORITHM:
        _raise("Package signature sidecar declares an unsupported algorithm.")
    key_id = raw.get("key_id")
    if not isinstance(key_id, str) or not _KEY_ID_RE.fullmatch(key_id):
        _raise("Package signature key_id is invalid.")
    if raw.get("agent_id") != agent_id or raw.get("version") != version:
        _raise("Package signature identity does not match agent.json.")
    declared_digest = raw.get("package_sha256")
    if not isinstance(declared_digest, str) or not _SHA256_RE.fullmatch(declared_digest):
        _raise("Package signature package_sha256 must be lowercase SHA-256.")
    if declared_digest != package_sha256:
        _raise("Package signature does not match the resolved package content digest.", "LAP-302")
    signature_value = raw.get("signature")
    if not isinstance(signature_value, str):
        _raise("Package signature value is invalid.")
    _base64url_decode(signature_value, label="Package signature value", expected_bytes=64)
    return PackageSignature(
        key_id=key_id,
        agent_id=agent_id,
        version=version,
        package_sha256=package_sha256,
        signature=signature_value,
        sidecar_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _trusted_public_key(value: str | bytes, *, key_id: str) -> bytes:
    if isinstance(value, bytes):
        decoded = value
    elif isinstance(value, str):
        decoded = _base64url_decode(value, label=f"Trusted publisher key {key_id}",
                                    expected_bytes=32)
    else:
        _raise(f"Trusted publisher key {key_id} must be base64url.", "LAP-201")
    if len(decoded) != 32:
        _raise(f"Trusted publisher key {key_id} has an invalid byte length.", "LAP-201")
    return decoded


def normalize_trusted_publisher_keys(value: object) -> dict[str, str]:
    """Validate Host config without retaining decoded key material globally."""
    if not isinstance(value, dict):
        _raise("Trusted publisher keys must map key IDs to base64url Ed25519 keys.")
    normalized: dict[str, str] = {}
    for raw_key_id, raw_public_key in value.items():
        key_id = raw_key_id.strip() if isinstance(raw_key_id, str) else ""
        if not _KEY_ID_RE.fullmatch(key_id):
            _raise("Trusted publisher keys contain an invalid key ID.")
        if not isinstance(raw_public_key, str):
            _raise(f"Trusted publisher key {key_id} must be base64url.")
        _trusted_public_key(raw_public_key.strip(), key_id=key_id)
        normalized[key_id] = raw_public_key.strip()
    return normalized


def verify_package_signature(package_root: str | Path, *, agent_id: str, version: str,
                             package_sha256: str,
                             trusted_public_keys: Mapping[str, str | bytes],
                             require_trusted: bool) -> PackageSignatureVerification:
    """Verify the sidecar against an explicit Host publisher-key trust map."""
    signature = read_package_signature(
        package_root,
        agent_id=agent_id,
        version=version,
        package_sha256=package_sha256,
    )
    if signature is None:
        if require_trusted:
            _raise("Host policy requires a trusted signed external Agent package.", "LAP-302")
        return PackageSignatureVerification(status="unsigned")
    configured_key = trusted_public_keys.get(signature.key_id)
    if configured_key is None:
        if require_trusted:
            _raise(f"Package signing key {signature.key_id} is not trusted by this Host.", "LAP-302")
        return PackageSignatureVerification(status="untrusted", signature=signature)
    public_key = _trusted_public_key(configured_key, key_id=signature.key_id)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            _base64url_decode(signature.signature, label="Package signature value", expected_bytes=64),
            _signature_message(
                key_id=signature.key_id,
                agent_id=signature.agent_id,
                version=signature.version,
                package_sha256=signature.package_sha256,
            ),
        )
    except InvalidSignature as exc:
        raise PackageSigningError(
            "LAP-302",
            f"Package signature verification failed for trusted key {signature.key_id}.",
        ) from exc
    return PackageSignatureVerification(status="verified", signature=signature)


def public_key_base64url(private_key: Ed25519PrivateKey) -> str:
    """Return the Host configuration value for a generated Ed25519 key."""
    if not isinstance(private_key, Ed25519PrivateKey):
        _raise("Package signing private key must be Ed25519.")
    return _base64url_encode(private_key.public_key().public_bytes_raw())
