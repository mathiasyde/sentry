"""A new detection rule needs changes only in core/report/rules/ (US4, SC-006)."""

from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import LOGS_DIR, SENTRY_DIR

SAMPLE_RULE = '''"""core/report/rules: sample rule used only by the extension-point test."""

from __future__ import annotations


def detect_sample(event, data, tracked, findings):
    findings.add(
        "WV-SAMPLE",
        "info",
        "Sample rule",
        "Sample description.",
        "Sample recommendation.",
        {"url": data.get("url")},
    )
'''

REGISTRATION = '''
from core.report.rules import sample  # noqa: E402

register(EventType.URL_LOADED, sample.detect_sample)
'''


def changed_files(original: Path, copy: Path) -> list[str]:
    changed = []

    def walk(cmp: filecmp.dircmp, prefix: str) -> None:
        changed.extend(prefix + name for name in cmp.diff_files + cmp.right_only + cmp.left_only if name != "__pycache__")
        for name, sub in cmp.subdirs.items():
            if name != "__pycache__":
                walk(sub, f"{prefix}{name}/")

    walk(filecmp.dircmp(original, copy, ignore=["__pycache__", "build"]), "")
    return sorted(changed)


class ExtensionPoint(unittest.TestCase):
    def test_new_rule_touches_only_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "sentry"
            shutil.copytree(SENTRY_DIR, copy, ignore=shutil.ignore_patterns("__pycache__", "build"))
            rules = copy / "core" / "report" / "rules"
            (rules / "sample.py").write_text(SAMPLE_RULE, encoding="utf-8")
            with (rules / "__init__.py").open("a", encoding="utf-8") as handle:
                handle.write(REGISTRATION)

            out = Path(tmp) / "out"
            result = subprocess.run(
                [
                    sys.executable,
                    str(copy / "report.py"),
                    str(LOGS_DIR / "synthetic" / "navigation.log"),
                    "--json",
                    str(out / "report.json"),
                    "--markdown",
                    str(out / "report.md"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertIn("WV-SAMPLE", {finding["rule_id"] for finding in report["findings"]})
            self.assertIn("WV-SAMPLE", (out / "report.md").read_text(encoding="utf-8"))

            changed = changed_files(SENTRY_DIR, copy)
            self.assertTrue(changed)
            for path in changed:
                self.assertTrue(path.startswith("core/report/rules/"), f"unexpected change outside rules/: {path}")


if __name__ == "__main__":
    unittest.main()
