"""The bundled browser sources behave exactly like the legacy page-side template scripts (FR-004, FR-008)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import LEGACY_DIR, REPO_ROOT, SENTRY_DIR, have_node

HARNESS = REPO_ROOT / "tests" / "tools" / "browser_harness.js"


def run_harness(mode: str, path: Path) -> str:
    result = subprocess.run(["node", str(HARNESS), mode, str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"harness ({mode}) failed:\n{result.stderr}")
    return result.stdout


@unittest.skipUnless(have_node(), "node is not installed")
class BrowserParity(unittest.TestCase):
    def test_bundle_matches_legacy(self) -> None:
        legacy = run_harness("legacy", LEGACY_DIR / "webview.js")
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "agent.js"
            build = subprocess.run(
                [sys.executable, str(SENTRY_DIR / "core" / "agent" / "build_agent.py"), "--out", str(agent)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            bundled = run_harness("bundle", agent)

        legacy_data = json.loads(legacy)
        self.assertGreaterEqual(len(legacy_data["probe"]["events"]), 8, "legacy harness produced too few page events")
        self.assertEqual(json.loads(bundled), legacy_data)


if __name__ == "__main__":
    unittest.main()
