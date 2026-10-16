"""core/run: AnalysisSession, a template method fixing the order of the steps of one analysis run."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from core.host import Host, require_commands
from core.run.discovery import run_discovery
from core.run.options import USAGE_OPTIONS, OptionError, parse_args
from core.run.package import apk_package_name, find_aapt
from core.run.reporting import report_on_exit
from core.run.workspace import Workspace
from core.runners import RunContext, select_runner


class AnalysisSession:
    def __init__(self, host: Host, prog: str, workspace: Workspace | None = None) -> None:
        self.host = host
        self.prog = prog
        self.workspace = workspace or Workspace(Path("."))

    def run(self, argv: list[str]) -> int:
        self.host.echo("Sentry - version alpha", "")
        try:
            args, discover = parse_args(argv)
        except OptionError as exc:
            self.host.die(f"Error: {exc}")
        kvm_available = self.host.has_kvm()
        require_commands(self.host, "python3")

        apk = self.validate_apk(args)
        package = self.resolve_package(args, apk)
        runner = select_runner(self.host.getenv("SENTRY_RUNNER") or "auto", self.host, kvm_available)
        context = RunContext(self.host, self.workspace, apk, package, kvm_available)

        runner.preflight(context)
        self.workspace.prepare(apk, package)
        with report_on_exit(self.host, self.workspace):
            if discover:
                run_discovery(self.host, self.workspace)
            runner.run(context)
        return 0

    def validate_apk(self, args: list[str]) -> str:
        apk = args[0] if args else ""
        if apk == "":
            self.host.die(f"Usage: {self.prog} <apk> [<apk-package>]", USAGE_OPTIONS)
        if not Path(apk).is_file():
            self.host.die(f"File not found: {apk}")
        return apk

    def resolve_package(self, args: list[str], apk: str) -> str:
        package = args[1] if len(args) > 1 else ""
        if package == "":
            aapt = find_aapt(self.host)
            if not aapt:
                self.host.die("Failed to find aapt. Install it with Homebrew or provide the APK package name.")
            package = apk_package_name(self.host, aapt, apk)
        if package == "":
            self.host.die("Failed to extract package name from apk")
        return package


def exit_on_signal(code: int):
    def handler(signum, frame):
        raise SystemExit(code)

    return handler


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGINT, exit_on_signal(130))
    signal.signal(signal.SIGTERM, exit_on_signal(143))
    host = Host()
    prog = host.getenv("SENTRY_PROG") or "analyse.sh"
    return AnalysisSession(host, prog).run(sys.argv[1:] if argv is None else argv)
