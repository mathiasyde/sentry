"""AnalysisSession runs the intent-data profile alongside static bridge discovery, gated by --verbose.

A failure here never warns, with or without --verbose: it is fixed silently (the artifact still
records "failed", for anyone who goes looking).
"""

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


class NoOpRunner:
    name = "fake"

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def preflight(self, context) -> None:
        pass

    def run(self, context) -> None:
        pass


class IntentProfileInSession(unittest.TestCase):
    def run_session(self, argv_extra: list[str], apk: Path = APK, stale: bool = False):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        apk_copy = tmp / "input.apk"
        shutil.copyfile(apk, apk_copy)
        workspace = Workspace(tmp)
        if stale:
            workspace.target.mkdir(parents=True)
            workspace.intent_profile.write_text("stale", encoding="utf-8")
        out = io.StringIO()
        with (
            mock.patch("core.run.session.select_runner", return_value=NoOpRunner(workspace)),
            mock.patch("core.run.reporting.report_cli.main"),
            redirect_stdout(out),
        ):
            code = AnalysisSession(FakeHost(), "analyse.sh", workspace).run([*argv_extra, str(apk_copy), "com.example.strongupdate"])
        return code, out.getvalue().splitlines(), workspace

    def test_silent_by_default_but_artifact_is_written(self) -> None:
        code, lines, workspace = self.run_session([])
        self.assertEqual(code, 0)
        self.assertFalse(any(line.startswith("Intent data profile") for line in lines), lines)
        artifact = json.loads(workspace.intent_profile.read_text(encoding="utf-8"))
        self.assertEqual(artifact["status"], "completed")

    def test_verbose_logs_the_summary(self) -> None:
        code, lines, _workspace = self.run_session(["--verbose"])
        self.assertEqual(code, 0)
        self.assertTrue(
            any(line.startswith("Intent data profile: ") and line.endswith("target/intent-data-profile.json") for line in lines),
            lines,
        )

    def test_failure_is_silent_even_with_verbose(self) -> None:
        for argv_extra in ([], ["--verbose"]):
            with self.subTest(argv_extra=argv_extra):
                code, lines, workspace = self.run_session(argv_extra, apk=REPO_ROOT / "README.md")
                self.assertEqual(code, 0)
                self.assertFalse(any("intent data profile" in line.lower() for line in lines), lines)
                self.assertEqual(json.loads(workspace.intent_profile.read_text(encoding="utf-8"))["status"], "failed")

    def test_disabling_bridge_discovery_skips_it_too(self) -> None:
        code, lines, workspace = self.run_session(["--no-discover-bridge-interfaces"], stale=True)
        self.assertEqual(code, 0)
        self.assertFalse(workspace.intent_profile.exists(), "prepare() must remove a stale artifact")


if __name__ == "__main__":
    unittest.main()
