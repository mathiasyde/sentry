"""core/ keeps detection, rendering, I/O and orchestration apart (FR-010, FR-012, FR-013, SC-007)."""

from __future__ import annotations

import re
import unittest

from tests.helpers import SENTRY_DIR
from tests.layering_helpers import assert_has_header, assert_max_lines, assert_no_pattern, iter_files

CORE = SENTRY_DIR / "core"
REPORT = CORE / "report"


class CoreLayering(unittest.TestCase):
    def test_rules_do_no_io(self) -> None:
        files = iter_files(REPORT / "rules", [".py"])
        for pattern in (r"\bopen\(", r"\.write_text\(", r"\.write\(", r"\bprint\(", r"\bPath\("):
            assert_no_pattern(self, files, pattern, "detectors must not do file I/O or print")

    def test_rendering_and_tracking_do_not_detect(self) -> None:
        for name in ("markdown.py", "assemble.py", "tracker.py"):
            text = (REPORT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"^\s*(from|import)\s+core\.report\.(rules|findings)\b", text, re.M), f"{name} imports rules/findings")

    def test_report_independent_of_instrumentation(self) -> None:
        assert_no_pattern(self, iter_files(REPORT, [".py"]), r"\b(browser|native)/", "report must not depend on browser/ or native/")

    def test_sizes(self) -> None:
        assert_max_lines(self, iter_files(REPORT, [".py"]), 340)
        assert_max_lines(self, iter_files(CORE / "run", [".py"]), 100)
        assert_max_lines(self, iter_files(CORE / "runners", [".py"]), 100)
        assert_max_lines(self, iter_files(CORE / "benchmark", [".py"]), 160)
        assert_max_lines(self, [CORE / "host.py"], 160)
        assert_max_lines(self, iter_files(CORE / "static", [".py"]), 340)

    def test_static_is_self_contained(self) -> None:
        files = iter_files(CORE / "static", [".py"])
        assert_no_pattern(self, files, r"^\s*(from|import)\s+core\.(run|runners|benchmark)\b", "static/ must not depend on orchestration")
        allowed = "from core.report.rules.catalog import SENSITIVE_METHOD_RE"
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.match(r"^\s*(from|import)\s+core\.report\b", line):
                    self.assertEqual(line.strip(), allowed, f"{path}: static/ may only import the sensitive-name pattern from report/")

    def test_report_does_not_import_static(self) -> None:
        assert_no_pattern(self, iter_files(REPORT, [".py"]), r"core\.static", "report/ reads the static artifact, never the static package")

    def test_no_shell_scripts_in_core(self) -> None:
        self.assertEqual(iter_files(CORE, [".sh"]), [], "orchestration is Python; shell is only for the root launchers")

    def test_only_host_touches_processes(self) -> None:
        files = [path for path in iter_files(CORE, [".py"]) if path.name != "host.py" and "report" not in path.parts]
        assert_no_pattern(self, files, r"\bsubprocess\b|\bos\.system\b", "use core.host.Host for processes")

    def test_headers(self) -> None:
        for path in iter_files(CORE, [".py", ".sh", ".js"]):
            assert_has_header(self, path)


if __name__ == "__main__":
    unittest.main()
