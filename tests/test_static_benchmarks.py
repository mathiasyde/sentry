"""core/static on the committed Benchmark APKs against hand-made ground truth (SC-001, SC-002, SC-003, SC-005)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import FIXTURES, REPO_ROOT, SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static import discover_bridges  # noqa: E402

BENCHMARK = REPO_ROOT / "Benchmark"
GROUND_TRUTH = json.loads((FIXTURES / "static" / "ground_truth.json").read_text(encoding="utf-8"))
TIME_BUDGET = 30.0


def summary(registrations: list[dict]) -> set[tuple]:
    return {
        (r["name"], r["class_name"], r["class_resolution"], tuple(sorted(m if isinstance(m, str) else m["name"] for m in r["methods"])))
        for r in registrations
    }


class Benchmarks(unittest.TestCase):
    def test_ground_truth(self) -> None:
        apks = sorted(BENCHMARK.glob("*.apk"))
        self.assertEqual({apk.name for apk in apks}, set(GROUND_TRUTH))
        for apk in apks:
            with self.subTest(apk=apk.name):
                started = time.monotonic()
                result = discover_bridges(apk)
                seconds = time.monotonic() - started
                self.assertEqual(result["status"], "completed")
                self.assertEqual(summary(result["registrations"]), summary(GROUND_TRUTH[apk.name]["registrations"]))
                self.assertLess(seconds, TIME_BUDGET, f"{apk.name} took {seconds:.1f}s")

    def test_truncated_apk_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.apk"
            broken.write_bytes((BENCHMARK / "strongUpdate.apk").read_bytes()[:4096])
            with self.assertRaises(Exception):
                discover_bridges(broken)
            env = {**os.environ, "PYTHONPATH": str(SENTRY_DIR)}
            result = subprocess.run([sys.executable, "-m", "core.static", str(broken)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 2, result.stderr)
        artifact = json.loads(result.stdout)
        self.assertEqual(artifact["status"], "failed")
        self.assertTrue(artifact["error"])
        self.assertLessEqual(len(artifact["error"]), 200)

    def test_missing_file(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(SENTRY_DIR)}
        result = subprocess.run([sys.executable, "-m", "core.static", "missing.apk"], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: file not found: missing.apk", result.stdout)


if __name__ == "__main__":
    unittest.main()
