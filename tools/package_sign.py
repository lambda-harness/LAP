"""Compatibility wrapper for the installed LAP package-signing command."""

from __future__ import annotations

from lap_protocol.package_sign_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
