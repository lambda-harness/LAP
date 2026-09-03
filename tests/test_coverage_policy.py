"""Black-box tests for the CI coverage policy command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_coverage_xml(path: Path, *, line_rate: str, branch_rate: str) -> None:
    path.write_text(
        f'<coverage line-rate="{line_rate}" branch-rate="{branch_rate}" />',
        encoding="utf-8",
    )


def _run_policy(coverage_xml: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "check_coverage.py"),
            "--input",
            str(coverage_xml),
            "--minimum-line-rate",
            "90",
            "--minimum-branch-rate",
            "80",
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_coverage_policy_accepts_independent_line_and_branch_thresholds(
    tmp_path: Path,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    _write_coverage_xml(coverage_xml, line_rate="0.91", branch_rate="0.81")

    completed = _run_policy(coverage_xml)

    assert completed.returncode == 0
    assert "line 91.00%" in completed.stdout
    assert "branch 81.00%" in completed.stdout


def test_coverage_policy_rejects_a_failed_branch_threshold(tmp_path: Path) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    _write_coverage_xml(coverage_xml, line_rate="0.99", branch_rate="0.79")

    completed = _run_policy(coverage_xml)

    assert completed.returncode == 1
    assert "branch 79.00%" in completed.stdout


def test_coverage_policy_rejects_invalid_xml_rates(tmp_path: Path) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    _write_coverage_xml(coverage_xml, line_rate="not-a-rate", branch_rate="0.90")

    completed = _run_policy(coverage_xml)

    assert completed.returncode == 1
    assert "coverage policy error" in completed.stdout
