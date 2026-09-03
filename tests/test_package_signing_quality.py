"""Boundary coverage for the installable LAP Package Signing helpers."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lap_protocol.package_sign_cli import main as package_sign_main
from lap_protocol.package_signing import (
    PackageSignature,
    PackageSigningError,
    create_package_signature,
    normalize_trusted_publisher_keys,
    package_content_sha256,
    public_key_base64url,
    read_package_signature,
    verify_package_signature,
    write_package_signature,
)

_AGENT_ID = "com.example.signed-agent"
_KEY_ID = "com.example.publisher"
_VERSION = "1.2.3"


def _write_package(root: Path) -> Path:
    package = root / "agent"
    package.mkdir(parents=True)
    (package / "agent.json").write_text(
        json.dumps(
            {
                "lap": "0.1",
                "id": _AGENT_ID,
                "display_name": "Signed Agent",
                "version": _VERSION,
                "transport": {"kind": "lap-local", "command": ["bin/agent"]},
                "capabilities": [{"id": "task.run", "description": "Run one task."}],
            }
        ),
        encoding="utf-8",
    )
    (package / "bin").mkdir()
    (package / "bin" / "agent").write_bytes(b"agent-v1")
    return package


def _create_signature(
    package: Path,
    private_key: Ed25519PrivateKey,
    *,
    key_id: str = _KEY_ID,
) -> PackageSignature:
    return create_package_signature(
        key_id=key_id,
        agent_id=_AGENT_ID,
        version=_VERSION,
        package_sha256=package_content_sha256(package),
        private_key=private_key,
    )


def _write_signed_package(
    package: Path,
    private_key: Ed25519PrivateKey,
    *,
    key_id: str = _KEY_ID,
) -> PackageSignature:
    return write_package_signature(
        package,
        _create_signature(package, private_key, key_id=key_id),
    )


def _read_sidecar(package: Path) -> dict[str, Any]:
    value = json.loads((package / "lap-signature.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _expect_error(callback: object, code: str) -> None:
    assert callable(callback)
    with pytest.raises(PackageSigningError) as raised:
        callback()
    assert raised.value.code == code


def test_package_content_rejects_invalid_roots_and_limits(tmp_path: Path) -> None:
    _expect_error(lambda: package_content_sha256(tmp_path / "missing"), "LAP-201")
    ordinary_file = tmp_path / "not-a-directory"
    ordinary_file.write_text("not an Agent package", encoding="utf-8")
    _expect_error(lambda: package_content_sha256(ordinary_file), "LAP-201")

    package = _write_package(tmp_path)
    _expect_error(lambda: package_content_sha256(package, maximum_files=1), "LAP-201")
    _expect_error(lambda: package_content_sha256(package, maximum_bytes=1), "LAP-401")


def test_create_signature_rejects_invalid_bound_values(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    key = Ed25519PrivateKey.generate()
    digest = package_content_sha256(package)

    _expect_error(
        lambda: create_package_signature(
            key_id="x",
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            private_key=key,
        ),
        "LAP-201",
    )
    _expect_error(
        lambda: create_package_signature(
            key_id=_KEY_ID,
            agent_id="x",
            version=_VERSION,
            package_sha256=digest,
            private_key=key,
        ),
        "LAP-201",
    )
    _expect_error(
        lambda: create_package_signature(
            key_id=_KEY_ID,
            agent_id=_AGENT_ID,
            version="draft",
            package_sha256=digest,
            private_key=key,
        ),
        "LAP-201",
    )
    _expect_error(
        lambda: create_package_signature(
            key_id=_KEY_ID,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256="not-a-digest",
            private_key=key,
        ),
        "LAP-201",
    )
    _expect_error(
        lambda: create_package_signature(
            key_id=_KEY_ID,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            private_key=object(),
        ),
        "LAP-201",
    )


def test_sidecar_rejects_duplicate_and_malformed_records(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    key = Ed25519PrivateKey.generate()
    signature = _write_signed_package(package, key)
    _expect_error(lambda: write_package_signature(package, signature), "LAP-201")
    replacement = write_package_signature(package, signature, overwrite=True)
    assert replacement.sidecar_sha256

    expected_digest = package_content_sha256(package)
    payload = _read_sidecar(package)
    malformed_records: tuple[tuple[str, Any, str], ...] = (
        ("lap", "0.2", "LAP-102"),
        ("algorithm", "rsa", "LAP-201"),
        ("key_id", "x", "LAP-201"),
        ("agent_id", "com.example.other", "LAP-201"),
        ("package_sha256", "not-a-digest", "LAP-201"),
        ("package_sha256", "0" * 64, "LAP-302"),
        ("signature", "not-base64!", "LAP-201"),
        ("signature", None, "LAP-201"),
    )
    for field, value, code in malformed_records:
        modified = dict(payload)
        modified[field] = value
        (package / "lap-signature.json").write_text(
            json.dumps(modified), encoding="utf-8"
        )
        _expect_error(
            lambda: read_package_signature(
                package,
                agent_id=_AGENT_ID,
                version=_VERSION,
                package_sha256=expected_digest,
            ),
            code,
        )

    (package / "lap-signature.json").write_text("[]", encoding="utf-8")
    _expect_error(
        lambda: read_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=expected_digest,
        ),
        "LAP-201",
    )
    (package / "lap-signature.json").write_text("not-json", encoding="utf-8")
    _expect_error(
        lambda: read_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=expected_digest,
        ),
        "LAP-201",
    )
    (package / "lap-signature.json").write_bytes(b"x" * 100_000)
    _expect_error(
        lambda: read_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=expected_digest,
        ),
        "LAP-201",
    )


def test_sidecar_rejects_non_file_targets(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    sidecar = package / "lap-signature.json"
    sidecar.mkdir()
    key = Ed25519PrivateKey.generate()
    signature = _create_signature(package, key)

    _expect_error(lambda: write_package_signature(package, signature), "LAP-201")
    _expect_error(
        lambda: read_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=package_content_sha256(package),
        ),
        "LAP-201",
    )


def test_trust_configuration_and_verification_cover_safe_statuses(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path)
    digest = package_content_sha256(package)
    assert (
        read_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
        )
        is None
    )
    assert verify_package_signature(
        package,
        agent_id=_AGENT_ID,
        version=_VERSION,
        package_sha256=digest,
        trusted_public_keys={},
        require_trusted=False,
    ).public() == {"status": "unsigned", "profile": "lap-package-signing/0.1"}
    _expect_error(
        lambda: verify_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            trusted_public_keys={},
            require_trusted=True,
        ),
        "LAP-302",
    )

    signing_key = Ed25519PrivateKey.generate()
    _write_signed_package(package, signing_key)
    assert (
        verify_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            trusted_public_keys={},
            require_trusted=False,
        ).status
        == "untrusted"
    )
    _expect_error(
        lambda: verify_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            trusted_public_keys={
                _KEY_ID: public_key_base64url(Ed25519PrivateKey.generate())
            },
            require_trusted=True,
        ),
        "LAP-302",
    )
    _expect_error(
        lambda: verify_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            trusted_public_keys={_KEY_ID: object()},
            require_trusted=True,
        ),
        "LAP-201",
    )
    _expect_error(
        lambda: verify_package_signature(
            package,
            agent_id=_AGENT_ID,
            version=_VERSION,
            package_sha256=digest,
            trusted_public_keys={_KEY_ID: b"short"},
            require_trusted=True,
        ),
        "LAP-201",
    )

    public_key = public_key_base64url(signing_key)
    assert normalize_trusted_publisher_keys({_KEY_ID: f"  {public_key}  "}) == {
        _KEY_ID: public_key
    }
    invalid_values: tuple[object, ...] = (
        [],
        {"x": public_key},
        {_KEY_ID: object()},
        {_KEY_ID: "not-base64!"},
        {_KEY_ID: "a"},
    )
    for invalid_value in invalid_values:
        _expect_error(
            lambda: normalize_trusted_publisher_keys(invalid_value), "LAP-201"
        )
    _expect_error(lambda: public_key_base64url(object()), "LAP-201")


def test_package_sign_cli_runs_installed_commands_and_returns_typed_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _write_package(tmp_path)
    private_key = tmp_path / "publisher.pem"
    public_key = tmp_path / "publisher.pub"

    assert (
        package_sign_main(
            [
                "keygen",
                "--private-key",
                str(private_key),
                "--public-key",
                str(public_key),
            ]
        )
        == 0
    )
    keygen = json.loads(capsys.readouterr().out)
    assert keygen["algorithm"] == "ed25519"
    assert (
        package_sign_main(
            [
                "keygen",
                "--private-key",
                str(private_key),
                "--public-key",
                str(public_key),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"

    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(package),
                "--private-key",
                str(private_key),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "signed"
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(package),
                "--private-key",
                str(private_key),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(package),
                "--private-key",
                str(private_key),
                "--key-id",
                _KEY_ID,
                "--overwrite",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        package_sign_main(
            [
                "verify",
                "--package",
                str(package),
                "--key-id",
                _KEY_ID,
                "--public-key",
                public_key.read_text(encoding="ascii").strip(),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "verified"

    dash_key = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(
            "0000000000000000000000000000000000000000000000000000000000000021"
        )
    )
    dash_private_key = tmp_path / "dash.pem"
    dash_private_key.write_bytes(
        dash_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    dash_package = _write_package(tmp_path / "dash")
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(dash_package),
                "--private-key",
                str(dash_private_key),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 0
    )
    capsys.readouterr()
    dash_public_key = public_key_base64url(dash_key)
    assert dash_public_key.startswith("-")
    assert (
        package_sign_main(
            [
                "verify",
                "--package",
                str(dash_package),
                "--key-id",
                _KEY_ID,
                "--public-key",
                dash_public_key,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "verified"


def test_package_sign_cli_rejects_missing_manifest_and_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_package = tmp_path / "empty"
    empty_package.mkdir()
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(empty_package),
                "--private-key",
                str(tmp_path / "missing.pem"),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"

    invalid_manifest = tmp_path / "invalid-manifest"
    invalid_manifest.mkdir()
    (invalid_manifest / "agent.json").write_text("{}", encoding="utf-8")
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(invalid_manifest),
                "--private-key",
                str(tmp_path / "missing.pem"),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"

    valid_package = _write_package(tmp_path / "valid")
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(valid_package),
                "--private-key",
                str(tmp_path / "missing.pem"),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"

    rsa_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_path = tmp_path / "publisher-rsa.pem"
    rsa_path.write_bytes(
        rsa_private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    assert (
        package_sign_main(
            [
                "sign",
                "--package",
                str(valid_package),
                "--private-key",
                str(rsa_path),
                "--key-id",
                _KEY_ID,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "LAP-201"


def test_package_sign_module_exposes_the_installed_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["lap-package-sign", "--help"])
    monkeypatch.delitem(sys.modules, "lap_protocol.package_sign_cli", raising=False)
    with pytest.raises(SystemExit) as raised:
        runpy.run_module("lap_protocol.package_sign_cli", run_name="__main__")
    assert raised.value.code == 0
