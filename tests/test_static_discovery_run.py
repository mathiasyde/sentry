"""AnalysisSession runs static discovery before the runner, and never lets it fail the run (FR-004, FR-011, FR-015, FR-016)."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import REPO_ROOT, SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.run.session import AnalysisSession  # noqa: E402
from core.run.workspace import Workspace  # noqa: E402
from tests.fakes import FakeHost  # noqa: E402

APK = REPO_ROOT / "Benchmark" / "strongUpdate.apk"
EVENT = '{"type": "url.loaded", "timestamp": "t", "data": {"webViewId": "w", "url": "file:///a"}}\n'


class RecordingRunner:
    name = "fake"

    def __init__(self, workspace: Workspace, out: io.StringIO) -> None:
        self.workspace = workspace
        self.out = out
        self.ran = False
        self.artifact_existed = False
        self.output_before = ""

    def preflight(self, context) -> None:
        pass

    def run(self, context) -> None:
        self.ran = True
        self.artifact_existed = self.workspace.static_bridges.is_file()
        self.output_before = self.out.getvalue()
        self.workspace.output_log.write_text(EVENT, encoding="utf-8")


class DiscoveryInSession(unittest.TestCase):
    def run_session(self, argv_extra: list[str], apk: Path = APK, stale: bool = False):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        apk_copy = tmp / "input.apk"
        shutil.copyfile(apk, apk_copy)
        workspace = Workspace(tmp)
        if stale:
            workspace.target.mkdir(parents=True)
            workspace.static_bridges.write_text("stale", encoding="utf-8")
        out = io.StringIO()
        runner = RecordingRunner(workspace, out)
        report_calls: list[list[str]] = []
        with (
            mock.patch("core.run.session.select_runner", return_value=runner),
            mock.patch("core.run.reporting.report_cli.main", side_effect=lambda argv: report_calls.append(argv)),
            redirect_stdout(out),
        ):
            code = AnalysisSession(FakeHost(), "analyse.sh", workspace).run([*argv_extra, str(apk_copy), "com.example.strongupdate"])
        return code, out.getvalue().splitlines(), runner, report_calls, workspace

    def test_default_runs_discovery_before_runner(self) -> None:
        code, lines, runner, report_calls, workspace = self.run_session([])
        self.assertEqual(code, 0)
        self.assertTrue(runner.artifact_existed)
        self.assertIn(
            "Static bridge discovery: 1 registration(s), 0 with unresolved names, 1 bridge class(es) -> target/static-bridges.json",
            runner.output_before.splitlines(),
        )
        artifact = json.loads(workspace.static_bridges.read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "completed")
        self.assertEqual(report_calls[0][-2:], ["--static-bridges", str(workspace.static_bridges)])

    def test_disabled_leaves_no_trace(self) -> None:
        code, lines, runner, report_calls, workspace = self.run_session(["--no-discover-bridge-interfaces"], stale=True)
        self.assertEqual(code, 0)
        self.assertTrue(runner.ran)
        self.assertFalse(workspace.static_bridges.exists(), "prepare() must remove a stale artifact")
        self.assertEqual(lines, ["Sentry - version alpha", ""])
        self.assertNotIn("--static-bridges", report_calls[0])

    def test_failure_does_not_stop_the_run(self) -> None:
        code, lines, runner, report_calls, workspace = self.run_session([], apk=REPO_ROOT / "README.md")
        self.assertEqual(code, 0)
        self.assertTrue(runner.ran)
        self.assertTrue(any(line.startswith("Warning: static bridge discovery failed: BadZipFile") for line in lines), lines)
        self.assertEqual(json.loads(workspace.static_bridges.read_text(encoding="utf-8"))["status"], "failed")
        self.assertIn("--static-bridges", report_calls[0])

    def test_invalid_value_exits_before_any_work(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            self.run_session(["--discover-bridge-interfaces=maybe"])
        self.assertEqual(caught.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
