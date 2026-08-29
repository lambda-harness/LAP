"""Verify the canonical repository and Go SDK identities published by LAP."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY = "https://github.com/lambda-harness/LAP"
CANONICAL_GO_MODULE = "github.com/lambda-harness/LAP/sdk/go"
# Keep this split so the test can inspect its own source with the same rule.
DEPRECATED_REPOSITORY = "github.com/" + "dongrv/LAP"
_TEXT_SUFFIXES = frozenset((
    ".md", ".toml", ".py", ".json", ".yml", ".yaml", ".go", ".rs",
))


def _tracked_text_files() -> list[Path]:
    """Inspect versioned source only, never generated artifacts or local data."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    files: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(raw_path.decode("utf-8"))
        if relative.suffix.lower() in _TEXT_SUFFIXES:
            files.append(ROOT / relative)
    return files


class RepositoryIdentityTests(unittest.TestCase):
    def test_tracked_text_has_no_deprecated_lap_repository_reference(self) -> None:
        offenders: list[str] = []
        for path in _tracked_text_files():
            if DEPRECATED_REPOSITORY in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual(
            offenders,
            [],
            f"Deprecated LAP repository reference found in: {', '.join(offenders)}",
        )

    def test_go_sdk_install_surface_has_the_canonical_module_identity(self) -> None:
        go_mod = (ROOT / "sdk" / "go" / "go.mod").read_text(encoding="utf-8")
        self.assertIn(f"module {CANONICAL_GO_MODULE}\n", go_mod)
        install = f"go get {CANONICAL_GO_MODULE}@main"
        import_path = f'"{CANONICAL_GO_MODULE}"'
        for path in (
            ROOT / "sdk" / "go" / "README.md",
            ROOT / "sdk" / "go" / "README.zh-CN.md",
        ):
            content = path.read_text(encoding="utf-8")
            self.assertIn(install, content)
            self.assertIn(import_path, content)

    def test_verification_workflow_installs_the_published_go_sdk(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("published-go-sdk:", workflow)
        self.assertIn(f"LAP_MODULE: {CANONICAL_GO_MODULE}", workflow)
        self.assertIn('go get "${LAP_MODULE}@${LAP_REVISION}"', workflow)
        self.assertIn(f'import _ "{CANONICAL_GO_MODULE}"', workflow)

    def test_published_schema_ids_use_the_canonical_repository(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                document.get("$id"),
                f"{CANONICAL_REPOSITORY}/schemas/{path.name}",
            )


if __name__ == "__main__":
    unittest.main()
