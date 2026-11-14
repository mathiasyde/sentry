"""BenchmarkSuite: preflight order, status mapping and per-APK archive layout (FR-006)."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.benchmark.suite import BenchmarkSuite, run_status  # noqa: E402
from core.host import Result  # noqa: E402
from tests.fakes import FakeHost  # noqa: E402


class Status(unittest.TestCase):
    def test_mapping(self) -> None:
        self.assertEqual([run_status(rc) for rc in (0, 124, 130, 1, 143)],
                         ["completed", "timed_out", "timed_out", "failed_1", "failed_143"])


class Suite(unittest.TestCase):
    def run_suite(self, host: FakeHost, root: Path, args: list[str]):
        out, err = io.StringIO(), io.StringIO()
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = BenchmarkSuite(host, root, "run-benchmarks-linux.sh").main(args)
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_preflight_errors_go_to_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.run_suite(FakeHost(linux=False), Path(tmp), [])
        self.assertEqual((code, out, err), (1, "", "Error: this benchmark runner is intended for Linux\n"))

    def test_first_missing_command_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Benchmark").mkdir()
            code, _, err = self.run_suite(FakeHost(commands={"python3"}), Path(tmp), [])
        self.assertEqual((code, err), (1, "Error: docker is not installed\n"))

    def test_runs_and_archives_each_apk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bench = root / "Benchmark"
            bench.mkdir()
            for name in ("b.apk", "a.apk", ".hidden.apk"):
                (bench / name).write_text("apk")
            aapt = root / "aapt"
            aapt.write_text("#!/bin/sh\n")
            aapt.chmod(0o755)
            (root / "target").mkdir()
            (root / "target" / "report.json").write_text("{}")
            (root / "target" / "static-bridges.json").write_text("{}")

            def respond(cmd):
                if cmd[:2] == [str(aapt), "dump"]:
                    return Result(0, f"package: name='com.{Path(cmd[-1]).stem}'\n")
                if cmd[0] == "timeout":
                    return Result(124 if "b.apk" in cmd[-2] else 0)
                return Result(0)

            host = FakeHost(env={"PATH": "/fake", "SENTRY_AAPT_FALLBACKS": str(aapt)}, respond=respond)
            code, out, err = self.run_suite(host, root, [])
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "==> a.apk (com.a)\n<== a.apk: completed\n==> b.apk (com.b)\n<== b.apk: timed_out\n")
            status = (root / "benchmark-results" / "b" / "status.txt").read_text()
            self.assertEqual(status, f"apk={bench}/b.apk\npackage=com.b\nstatus=timed_out\nseconds=600\n")
            self.assertTrue((root / "benchmark-results" / "a" / "runner.log").is_file())
            self.assertTrue((root / "benchmark-results" / "a" / "report.json").is_file())
            self.assertFalse((root / "benchmark-results" / "a" / "report.md").exists())
            self.assertTrue((root / "benchmark-results" / "a" / "static-bridges.json").is_file())
            timeouts = [c for c in host.calls if c[1][0] == "timeout"]
            self.assertEqual(timeouts[0][1], ["timeout", "-s", "INT", "600", "./analyse.sh", f"{bench}/a.apk", "com.a"])
            self.assertEqual(timeouts[0][2]["env"], {"SENTRY_RUNNER": "docker"})
            self.assertEqual(host.calls[-1][1], ["docker", "compose", "down"])


if __name__ == "__main__":
    unittest.main()
