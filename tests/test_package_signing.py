"""Executable checks for the optional LAP Package Signing Profile."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lap_package_signing import (
    PackageSigningError,
    create_package_signature,
    package_content_sha256,
    public_key_base64url,
    verify_package_signature,
    write_package_signature,
)


def write_package(root: Path) -> Path:
    package = root / "signed-agent"
    package.mkdir()
    (package / "agent.json").write_text(json.dumps({
        "lap": "0.1",
        "id": "com.example.signed-agent",
        "display_name": "Signed Agent",
        "version": "1.2.3",
        "transport": {"kind": "lap-local", "command": ["bin/agent"]},
        "capabilities": [{"id": "task.run", "description": "Runs one task."}],
    }), encoding="utf-8")
    (package / "bin").mkdir()
    (package / "bin" / "agent").write_bytes(b"fixture-agent-v1")
    return package


class PackageSigningTests(unittest.TestCase):
    def _sign(self, package: Path, *, key_id: str = "com.example.publisher",
              private_key: Ed25519PrivateKey | None = None) -> tuple[Ed25519PrivateKey, str]:
        key = private_key or Ed25519PrivateKey.generate()
        digest = package_content_sha256(package)
        write_package_signature(package, create_package_signature(
            key_id=key_id,
            agent_id="com.example.signed-agent",
            version="1.2.3",
            package_sha256=digest,
            private_key=key,
        ))
        return key, digest

    def test_sidecar_is_excluded_but_every_other_package_byte_is_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = write_package(Path(directory))
            key, digest = self._sign(package)
            self.assertEqual(package_content_sha256(package), digest)

            verification = verify_package_signature(
                package,
                agent_id="com.example.signed-agent",
                version="1.2.3",
                package_sha256=digest,
                trusted_public_keys={"com.example.publisher": public_key_base64url(key)},
                require_trusted=True,
            )
            self.assertEqual(verification.status, "verified")
            self.assertEqual(verification.signature.key_id, "com.example.publisher")

            payload = json.loads((package / "lap-signature.json").read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schemas" / "package-signature.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(payload)

            (package / "bin" / "agent").write_bytes(b"fixture-agent-v2")
            self.assertNotEqual(package_content_sha256(package), digest)
            with self.assertRaises(PackageSigningError) as raised:
                verify_package_signature(
                    package,
                    agent_id="com.example.signed-agent",
                    version="1.2.3",
                    package_sha256=package_content_sha256(package),
                    trusted_public_keys={"com.example.publisher": public_key_base64url(key)},
                    require_trusted=True,
                )
            self.assertEqual(raised.exception.code, "LAP-302")

    def test_required_policy_rejects_unsigned_or_unknown_publishers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = write_package(Path(directory))
            digest = package_content_sha256(package)
            with self.assertRaises(PackageSigningError) as raised:
                verify_package_signature(
                    package,
                    agent_id="com.example.signed-agent",
                    version="1.2.3",
                    package_sha256=digest,
                    trusted_public_keys={},
                    require_trusted=True,
                )
            self.assertEqual(raised.exception.code, "LAP-302")

            self._sign(package, key_id="com.example.unknown")
            with self.assertRaises(PackageSigningError) as raised:
                verify_package_signature(
                    package,
                    agent_id="com.example.signed-agent",
                    version="1.2.3",
                    package_sha256=digest,
                    trusted_public_keys={},
                    require_trusted=True,
                )
            self.assertEqual(raised.exception.code, "LAP-302")
            self.assertEqual(verify_package_signature(
                package,
                agent_id="com.example.signed-agent",
                version="1.2.3",
                package_sha256=digest,
                trusted_public_keys={},
                require_trusted=False,
            ).status, "untrusted")

    def test_reference_cli_generates_signs_and_verifies_a_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = write_package(root)
            private_key = root / "publisher.pem"
            public_key = root / "publisher.pub"
            tool = ROOT / "tools" / "package_sign.py"
            subprocess.run(
                [sys.executable, str(tool), "keygen", "--private-key", str(private_key),
                 "--public-key", str(public_key)],
                check=True,
                text=True,
                capture_output=True,
            )
            signed = subprocess.run(
                [sys.executable, str(tool), "sign", "--package", str(package),
                 "--private-key", str(private_key), "--key-id", "com.example.publisher"],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(signed.stdout)["status"], "signed")
            verified = subprocess.run(
                [sys.executable, str(tool), "verify", "--package", str(package),
                 "--key-id", "com.example.publisher",
                 "--public-key", public_key.read_text(encoding="ascii").strip()],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(verified.stdout)["status"], "verified")


if __name__ == "__main__":
    unittest.main()
