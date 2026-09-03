"""Validate LAP's separate line and branch coverage policy from coverage XML."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def _parse_rate(value: str | None, *, label: str) -> float:
    """Convert a coverage XML rate to a percentage.

    Args:
        value: Decimal rate recorded on the coverage root element.
        label: Human-readable metric name used in validation feedback.

    Returns:
        The metric expressed as a percentage.

    Raises:
        ValueError: If the XML value is absent, malformed, or outside 0 to 1.
    """
    try:
        rate = float(value) if value is not None else -1.0
    except ValueError as error:
        raise ValueError(f"Coverage XML has an invalid {label} rate.") from error
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"Coverage XML has an invalid {label} rate.")
    return rate * 100


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the coverage policy check."""
    parser = argparse.ArgumentParser(
        description="Enforce LAP's separate line and branch coverage thresholds."
    )
    parser.add_argument("--input", type=Path, default=Path("coverage.xml"))
    parser.add_argument("--minimum-line-rate", type=float, default=90.0)
    parser.add_argument("--minimum-branch-rate", type=float, default=80.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate a coverage XML document against LAP's quality thresholds.

    Args:
        argv: Optional command-line arguments excluding the program name.

    Returns:
        Zero when both thresholds are met; otherwise one.
    """
    args = _parse_args(argv)
    try:
        root = ET.parse(args.input).getroot()
        line_rate = _parse_rate(root.get("line-rate"), label="line")
        branch_rate = _parse_rate(root.get("branch-rate"), label="branch")
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"coverage policy error: {error}")
        return 1

    line_ok = line_rate >= args.minimum_line_rate
    branch_ok = branch_rate >= args.minimum_branch_rate
    print(
        "coverage policy: "
        f"line {line_rate:.2f}% (minimum {args.minimum_line_rate:.2f}%), "
        f"branch {branch_rate:.2f}% (minimum {args.minimum_branch_rate:.2f}%)"
    )
    return 0 if line_ok and branch_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
