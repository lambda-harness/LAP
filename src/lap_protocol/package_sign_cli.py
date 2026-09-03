"""Generate and verify optional LAP Package Signing Profile sidecars."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .package_signing import (
    PackageSigningError,
    create_package_signature,
    package_content_sha256,
    public_key_base64url,
    verify_package_signature,
    write_package_signature,
)

_PARSER_OPTIONS = frozenset(
    {
        "-h",
        "--help",
        "--package",
        "--private-key",
        "--public-key",
        "--key-id",
        "--overwrite",
    }
)
_CommandHandler = Callable[[argparse.Namespace], dict[str, str]]


def _normalize_dash_prefixed_public_key(argv: Sequence[str]) -> list[str]:
    """Prevent raw Base64URL public keys from being parsed as options."""
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--public-key" and index + 1 < len(argv):
            candidate = argv[index + 1]
            if candidate.startswith("-") and candidate not in _PARSER_OPTIONS:
                normalized.append(f"--public-key={candidate}")
                index += 2
                continue
        normalized.append(token)
        index += 1
    return normalized


def _manifest_identity(package: Path) -> tuple[str, str]:
    try:
        raw = json.loads((package / "agent.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageSigningError(
            "LAP-201", "Agent package agent.json could not be read."
        ) from error
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("id"), str)
        or not isinstance(raw.get("version"), str)
    ):
        raise PackageSigningError(
            "LAP-201", "Agent package agent.json must declare id and version."
        )
    return raw["id"], raw["version"]


def _write_new(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise PackageSigningError("LAP-201", f"Refusing to overwrite {path.name}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except OSError as error:
        raise PackageSigningError("LAP-500", f"Unable to write {path.name}.") from error


def _command_keygen(args: argparse.Namespace) -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_path = Path(cast(str, args.private_key))
    public_path = Path(cast(str, args.public_key))
    _write_new(
        private_path,
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    _write_new(
        public_path,
        (public_key_base64url(private_key) + "\n").encode("ascii"),
    )
    return {
        "algorithm": "ed25519",
        "private_key": str(private_path),
        "public_key": str(public_path),
        "host_public_key_base64url": public_key_base64url(private_key),
    }


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, TypeError, ValueError) as error:
        raise PackageSigningError(
            "LAP-201", "Private key must be an unencrypted Ed25519 PEM file."
        ) from error
    if not isinstance(key, Ed25519PrivateKey):
        raise PackageSigningError("LAP-201", "Private key must be Ed25519.")
    return key


def _command_sign(args: argparse.Namespace) -> dict[str, str]:
    package = Path(cast(str, args.package))
    agent_id, version = _manifest_identity(package)
    digest = package_content_sha256(package)
    signature = create_package_signature(
        key_id=cast(str, args.key_id),
        agent_id=agent_id,
        version=version,
        package_sha256=digest,
        private_key=_load_private_key(Path(cast(str, args.private_key))),
    )
    written = write_package_signature(
        package, signature, overwrite=cast(bool, args.overwrite)
    )
    return {
        **written.public(),
        "status": "signed",
        "sidecar_sha256": written.sidecar_sha256,
    }


def _command_verify(args: argparse.Namespace) -> dict[str, str]:
    package = Path(cast(str, args.package))
    agent_id, version = _manifest_identity(package)
    verification = verify_package_signature(
        package,
        agent_id=agent_id,
        version=version,
        package_sha256=package_content_sha256(package),
        trusted_public_keys={
            cast(str, args.key_id): cast(str, args.public_key),
        },
        require_trusted=True,
    )
    return verification.public()


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LAP Package Signing Profile reference tool"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    keygen = subcommands.add_parser("keygen", help="create an Ed25519 PEM key pair")
    keygen.add_argument("--private-key", required=True)
    keygen.add_argument("--public-key", required=True)
    keygen.set_defaults(handler=_command_keygen)

    sign = subcommands.add_parser(
        "sign", help="write a root lap-signature.json sidecar"
    )
    sign.add_argument("--package", required=True)
    sign.add_argument("--private-key", required=True)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--overwrite", action="store_true")
    sign.set_defaults(handler=_command_sign)

    verify = subcommands.add_parser(
        "verify", help="verify a package against one Host key"
    )
    verify.add_argument("--package", required=True)
    verify.add_argument("--key-id", required=True)
    verify.add_argument(
        "--public-key",
        required=True,
        help="raw 32-byte Ed25519 public key as unpadded base64url",
    )
    verify.set_defaults(handler=_command_verify)
    return parser.parse_args(_normalize_dash_prefixed_public_key(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the package-signing command-line interface.

    Args:
        argv: Optional arguments excluding the program name. When omitted, the
            process command-line arguments are used.

    Returns:
        Zero when the requested operation succeeds, otherwise two for a typed
        package-signing failure.
    """
    arguments = sys.argv[1:] if argv is None else argv
    args = _parse_args(arguments)
    handler = cast(_CommandHandler, args.handler)
    try:
        result = handler(args)
    except PackageSigningError as error:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": {"code": error.code, "message": error.message},
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
