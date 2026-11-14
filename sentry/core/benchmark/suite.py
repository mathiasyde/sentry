"""core/benchmark: BenchmarkSuite: preflight checks, one timed analyse.sh run per APK, per-APK result archive."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from core.host import MERGE, Host
from core.run.package import apk_package_name, find_aapt

USAGE = """Usage: {prog} [benchmark-dir]

Runs every APK in the benchmark directory through analyse.sh on Linux.

Environment:
  SENTRY_BENCHMARK_SECONDS   Per-APK timeout in seconds (default: 600)
  SENTRY_BENCHMARK_RESULTS   Output directory (default: benchmark-results)
  SENTRY_BENCHMARK_DIR       Benchmark directory override"""

ARCHIVED = ("status.txt", "runner.log", "output.log", "logs-output.log", "report.json", "report.md", "static-bridges.json")


def run_status(returncode: int) -> str:
    if returncode == 0:
        return "completed"
    if returncode in (124, 130):
        return "timed_out"
    return f"failed_{returncode}"


class BenchmarkSuite:
    def __init__(self, host: Host, root: Path, prog: str) -> None:
        self.host = host
        self.root = root
        self.prog = prog
        self.benchmark_dir = host.getenv("SENTRY_BENCHMARK_DIR")
        self.results_dir = Path(host.getenv("SENTRY_BENCHMARK_RESULTS") or f"{root}/benchmark-results")
        self.run_seconds = host.getenv("SENTRY_BENCHMARK_SECONDS") or "600"
        self.aapt = ""

    def die(self, message: str) -> None:
        self.host.die(f"Error: {message}", err=True)

    def main(self, args: list[str]) -> int:
        first = args[0] if args else ""
        if first in ("-h", "--help"):
            self.host.echo(USAGE.format(prog=self.prog))
            return 0

        if first:
            self.benchmark_dir = first
        elif not self.benchmark_dir:
            self.benchmark_dir = str(self.root / "Benchmark") if (self.root / "Benchmark").is_dir() else str(self.root / "benchmarks")

        self.preflight()
        self.results_dir.mkdir(parents=True, exist_ok=True)

        apks = sorted(p.name for p in Path(self.benchmark_dir).glob("*.apk") if not p.name.startswith("."))
        if not apks:
            self.die(f"no APK files found in {self.benchmark_dir}")

        for name in apks:
            apk = f"{self.benchmark_dir}/{name}"
            package = apk_package_name(self.host, self.aapt, apk)
            if not package:
                self.die(f"could not extract package name from {apk}")
            self.run_one(apk, package)

        if self.host.getenv("SENTRY_KEEP_CONTAINERS") != "1":
            self.host.run(["docker", "compose", "down"], quiet=True, cwd=self.root)
        return 0

    def preflight(self) -> None:
        if not self.host.is_linux():
            self.die("this benchmark runner is intended for Linux")
        if not self.host.has_kvm():
            self.die("/dev/kvm is required for Docker emulator mode")
        if not Path(self.benchmark_dir).is_dir():
            self.die(f"benchmark directory not found: {self.benchmark_dir}")
        for command in ("docker", "timeout", "python3"):
            if self.host.which(command) is None:
                self.die(f"{command} is not installed")
        if self.host.run(["docker", "compose", "version"], quiet=True).returncode != 0:
            self.die("docker compose is not available")
        self.aapt = find_aapt(self.host) or ""
        if not self.aapt:
            self.die("aapt is required on PATH or under ANDROID_HOME/ANDROID_SDK_ROOT")

    def run_one(self, apk: str, package: str) -> None:
        handle, log_path = tempfile.mkstemp()
        os.close(handle)
        self.host.echo(f"==> {os.path.basename(apk)} ({package})")
        with open(log_path, "wb") as log:
            returncode = self.host.run(
                ["timeout", "-s", "INT", self.run_seconds, "./analyse.sh", apk, package],
                stdout=log,
                stderr=MERGE,
                cwd=self.root,
                env={"SENTRY_RUNNER": "docker"},
            ).returncode
        status = run_status(returncode)
        self.archive(apk, package, status, Path(log_path))
        os.unlink(log_path)
        self.host.echo(f"<== {os.path.basename(apk)}: {status}")

    def archive(self, apk: str, package: str, status: str, runner_log: Path) -> None:
        name = os.path.basename(apk)
        name = name[: -len(".apk")] if name.endswith(".apk") and name != ".apk" else name
        out_dir = self.results_dir / name
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in ARCHIVED:
            (out_dir / item).unlink(missing_ok=True)

        (out_dir / "status.txt").write_text(
            f"apk={apk}\npackage={package}\nstatus={status}\nseconds={self.run_seconds}\n", encoding="utf-8"
        )
        shutil.copyfile(runner_log, out_dir / "runner.log")
        for source, target in (
            ("target/output.log", "output.log"),
            ("logs/output.log", "logs-output.log"),
            ("target/report.json", "report.json"),
            ("logs/report.md", "report.md"),
            ("target/static-bridges.json", "static-bridges.json"),
        ):
            if (self.root / source).is_file():
                shutil.copyfile(self.root / source, out_dir / target)


def main(argv: list[str] | None = None) -> int:
    host = Host()
    root = Path(host.getenv("SENTRY_ROOT") or Path(__file__).resolve().parents[3])
    prog = host.getenv("SENTRY_PROG") or "run-benchmarks-linux.sh"
    return BenchmarkSuite(host, root, prog).main(sys.argv[1:] if argv is None else argv)
