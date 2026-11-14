"""Golden regression check: reports must stay byte-identical to the pre-refactor outputs (FR-003, FR-016, FR-017)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import (
    EXPECTED_DIR,
    LOGS_DIR,
    REPO_ROOT,
    SENTRY_DIR,
    case_name,
    iter_logs,
    normalize_stdout,
    run_report,
)

REPORT_SCRIPT = SENTRY_DIR / "report.py"

ALL_RULE_IDS = {
    "WV-BRIDGE-CALLED-BY-REMOTE-CONTENT",
    "WV-CLEARTEXT-URL",
    "WV-CONTENT-ACCESS",
    "WV-FILE-ACCESS",
    "WV-FILE-FROM-FILE",
    "WV-FILE-URL-LOADED",
    "WV-GEOLOCATION-ENABLED",
    "WV-INLINE-CONTENT",
    "WV-JS-BRIDGE-EXPOSED",
    "WV-JS-CLEARTEXT-NETWORK",
    "WV-JS-ENABLED",
    "WV-JS-EVAL",
    "WV-JS-EVALUATED",
    "WV-JS-POPUPS",
    "WV-MIXED-CONTENT",
    "WV-PROBE-ERROR",
    "WV-SAFE-BROWSING-DISABLED",
    "WV-SENSITIVE-BRIDGE-METHOD",
    "WV-TAINTED-BRIDGE-DATA-TO-JS-SINK",
    "WV-UNIVERSAL-FILE-ACCESS",
    "WV-WEB-PERMISSION-GRANTED",
    "WV-WEB-PERMISSION-REQUEST",
}


class GoldenReports(unittest.TestCase):
    def test_reports_match_expected(self) -> None:
        logs = iter_logs()
        self.assertTrue(logs, "no fixture logs found")
        for log in logs:
            case = case_name(log)
            with self.subTest(case=case):
                expected = EXPECTED_DIR / case
                self.assertTrue(expected.is_dir(), f"missing expected output for {case}; run tests/tools/regen_expected.py")
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp)
                    result = run_report(REPORT_SCRIPT, log, out)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((out / "report.json").read_bytes(), (expected / "report.json").read_bytes(), "report.json differs")
                    self.assertEqual((out / "report.md").read_bytes(), (expected / "report.md").read_bytes(), "report.md differs")
                    self.assertEqual(normalize_stdout(result.stdout, out), (expected / "stdout.txt").read_text(encoding="utf-8"))

    def test_rule_coverage(self) -> None:
        seen: set[str] = set()
        for report in EXPECTED_DIR.glob("*/report.json"):
            seen |= {finding["rule_id"] for finding in json.loads(report.read_text(encoding="utf-8"))["findings"]}
        self.assertEqual(ALL_RULE_IDS - seen, set(), "rule ids not covered by any expected report")

    def test_benchmark_logs_complete(self) -> None:
        if os.environ.get("SENTRY_ALLOW_MISSING_BENCHMARK_LOGS") == "1":
            self.skipTest("SENTRY_ALLOW_MISSING_BENCHMARK_LOGS=1")
        missing = [
            apk.name
            for apk in sorted((REPO_ROOT / "Benchmark").glob("*.apk"))
            if not (LOGS_DIR / "benchmark" / f"{apk.stem}.log").exists()
        ]
        self.assertEqual(missing, [], "benchmark captures missing (task T014)")


if __name__ == "__main__":
    unittest.main()
