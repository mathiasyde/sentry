"""Report --static-bridges: inventory section, static/runtime provenance and the info finding (FR-012..FR-014, SC-004).

Static goldens in tests/fixtures/expected_static/ come from the current code (the legacy oracle has no static
support). Regenerate them with SENTRY_UPDATE_STATIC_GOLDENS=1 and review the diff.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import EXPECTED_DIR, FIXTURES, LOGS_DIR, SENTRY_DIR, normalize_stdout, run_report

REPORT_SCRIPT = SENTRY_DIR / "report.py"
LOG = LOGS_DIR / "synthetic" / "bridge.log"
STATIC = FIXTURES / "static"
EXPECTED_STATIC = FIXTURES / "expected_static"
UPDATE = os.environ.get("SENTRY_UPDATE_STATIC_GOLDENS") == "1"
CASES = {
    "synthetic__static_inventory": "synthetic_inventory.json",
    "synthetic__static_failed": "synthetic_failed.json",
    "synthetic__static_mixed": "synthetic_mixed.json",
}


def report_with(static: Path | None, out: Path):
    extra = ["--static-bridges", str(static)] if static is not None else []
    result = run_report_args(out, extra)
    return result, json.loads((out / "report.json").read_text(encoding="utf-8")), (out / "report.md").read_text(encoding="utf-8")


def run_report_args(out: Path, extra: list[str]):
    assert not LOG.with_suffix(".args").exists(), "bridge.log is expected to take no extra arguments"
    out.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(REPORT_SCRIPT), str(LOG), "--json", str(out / "report.json"), "--markdown", str(out / "report.md"), *extra],
        capture_output=True,
        text=True,
    )


class StaticReport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_without_option_output_is_unchanged(self) -> None:
        result = run_report(REPORT_SCRIPT, LOG, self.out)
        expected = EXPECTED_DIR / "synthetic__bridge"
        self.assertEqual((self.out / "report.json").read_bytes(), (expected / "report.json").read_bytes())
        self.assertEqual((self.out / "report.md").read_bytes(), (expected / "report.md").read_bytes())
        self.assertEqual(normalize_stdout(result.stdout, self.out), (expected / "stdout.txt").read_text(encoding="utf-8"))

    def test_unusable_artifact_is_ignored(self) -> None:
        bad_schema = self.out / "schema2.json"
        bad_schema.write_text(json.dumps({"schema": 2}), encoding="utf-8")
        not_json = self.out / "broken.json"
        not_json.write_text("{", encoding="utf-8")
        expected = EXPECTED_DIR / "synthetic__bridge"
        for path, reason in ((self.out / "missing.json", "not found"), (bad_schema, "unsupported schema 2"), (not_json, "invalid JSON")):
            with self.subTest(reason=reason):
                out = self.out / reason.replace(" ", "_")
                result, _report, _md = report_with(path, out)
                self.assertIn(f"Warning: ignoring static bridge artifact: {reason}", result.stdout)
                self.assertEqual((out / "report.json").read_bytes(), (expected / "report.json").read_bytes())
                self.assertEqual((out / "report.md").read_bytes(), (expected / "report.md").read_bytes())

    def test_goldens(self) -> None:
        for case, artifact in CASES.items():
            with self.subTest(case=case):
                out = self.out / case
                result, _report, _md = report_with(STATIC / artifact, out)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = EXPECTED_STATIC / case
                if UPDATE:
                    expected.mkdir(parents=True, exist_ok=True)
                    for name in ("report.json", "report.md"):
                        (expected / name).write_bytes((out / name).read_bytes())
                for name in ("report.json", "report.md"):
                    self.assertEqual((out / name).read_bytes(), (expected / name).read_bytes(), f"{case}/{name} differs")

    def test_inventory_section(self) -> None:
        _result, report, markdown = report_with(STATIC / "synthetic_inventory.json", self.out)
        section = report["static_bridges"]
        self.assertEqual(
            set(section),
            {"status", "error", "target_sdk", "all_public_methods_exposed", "counts", "bridges", "unregistered_classes", "removals"},
        )
        self.assertLess(markdown.index("## Origin To Bridge Map"), markdown.index("## Static Bridge Inventory"))
        self.assertIn("> Target SDK is below 17", markdown)
        self.assertIn("one of: com.example.Legacy, com.example.Spare", markdown)
        self.assertIn("`<unresolved: method-result com.example.Cfg.bridgeName()>`", markdown)
        self.assertIn("### Bridge-capable classes with no discovered registration", markdown)
        self.assertIn("- `Legacy` in com.example.Main.onDestroy()", markdown)
        runtime_only = [b for b in section["bridges"] if b["provenance"] == "runtime-only"]
        self.assertEqual({b["interfaceName"] for b in runtime_only}, {"AppBridge", "Other"})

    def test_failed_artifact(self) -> None:
        _result, report, markdown = report_with(STATIC / "synthetic_failed.json", self.out)
        self.assertIn("- Discovery status: failed — BadZipFile: File is not a zip file", markdown)
        self.assertEqual({b["provenance"] for b in report["static_bridges"]["bridges"]}, {"runtime-only"})
        self.assertNotIn("WV-STATIC-BRIDGE-UNOBSERVED", {f["rule_id"] for f in report["findings"]})

    def test_mixed_provenance_and_finding(self) -> None:
        _result, plain, _ = report_with(None, self.out / "plain")
        _result, report, _md = report_with(STATIC / "synthetic_mixed.json", self.out / "mixed")
        section = report["static_bridges"]
        by_name = {b["interfaceName"]: b for b in section["bridges"]}
        self.assertEqual(by_name["AppBridge"]["provenance"], "static+runtime")
        self.assertEqual(by_name["Other"]["provenance"], "static+runtime")  # unresolved name, matched by class
        self.assertEqual(by_name["Hidden"]["provenance"], "static-only")
        self.assertEqual(
            [b["provenance"] for b in section["bridges"]], sorted((b["provenance"] for b in section["bridges"]), key=["static+runtime", "static-only", "runtime-only"].index)
        )
        counts = section["counts"]
        self.assertEqual((counts["static_and_runtime"], counts["static_only"], counts["runtime_only"]), (2, 1, 0))
        unobserved = [f for f in report["findings"] if f["rule_id"] == "WV-STATIC-BRIDGE-UNOBSERVED"]
        self.assertEqual(len(unobserved), 1)
        self.assertEqual(unobserved[0]["severity"], "info")
        evidence = unobserved[0]["evidence"][0]
        self.assertEqual(
            set(evidence),
            {"interfaceName", "className", "nameStatus", "classResolution", "candidateClasses", "callSite", "methods", "sensitiveMethods"},
        )
        self.assertEqual(evidence["callSite"], "com.example.Settings.openHelp()")
        self.assertEqual(evidence["sensitiveMethods"], ["deleteAll"])
        self.assertEqual(report["summary"]["risk_score"], plain["summary"]["risk_score"])
        self.assertEqual(by_name["AppBridge"]["sensitive_methods"], ["getToken"])


if __name__ == "__main__":
    unittest.main()
