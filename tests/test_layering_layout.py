"""The toolchain lives in exactly three areas under sentry/, each documented (FR-007, FR-015, FR-018, SC-004)."""

from __future__ import annotations

import unittest

from tests.helpers import REPO_ROOT, SENTRY_DIR

IGNORED = {"build", "__pycache__"}


class LayoutAndDocs(unittest.TestCase):
    def test_three_areas(self) -> None:
        dirs = {p.name for p in SENTRY_DIR.iterdir() if p.is_dir() and p.name not in IGNORED}
        self.assertEqual(dirs, {"browser", "native", "core"})

    def test_only_launchers_at_top_level(self) -> None:
        files = {p.name for p in SENTRY_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}
        self.assertEqual(files, {"Dockerfile", "report.py"})

    def test_legacy_locations_removed(self) -> None:
        for path in (SENTRY_DIR / "hooks", SENTRY_DIR / "run.sh", REPO_ROOT / "run-frida-server"):
            self.assertFalse(path.exists(), f"{path} should have been moved")

    def test_area_readmes(self) -> None:
        for area in ("browser", "native", "core"):
            self.assertTrue((SENTRY_DIR / area / "README.md").is_file(), f"missing sentry/{area}/README.md")

    def test_root_readme_layout_section(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Project layout", text)
        section = text.split("## Project layout", 1)[1].split("\n## ", 1)[0]
        for area in ("sentry/browser/", "sentry/native/", "sentry/core/"):
            self.assertIn(area, section)


if __name__ == "__main__":
    unittest.main()
