"""core/runners: local runner: host adb/frida against a running emulator or device; builds and loads the agent."""

from __future__ import annotations

from core.agent import build_agent
from core.host import require_commands
from core.runners.adb import Adb
from core.runners.base import RunContext, Runner


class LocalRunner(Runner):
    name = "local"

    def run(self, context: RunContext) -> None:
        host, workspace = context.host, context.workspace
        require_commands(host, "adb", "frida")

        host.echo("Using local emulator mode")
        if not context.kvm_available:
            host.echo("Docker/KVM is unavailable; using the host Android emulator via adb.")

        adb = Adb(host)
        if adb.run(["get-state"], quiet=True).returncode != 0:
            host.die(
                "Error: no Android emulator/device is visible to adb.",
                "Start an emulator first, or set SENTRY_RUNNER=docker on a Linux host with /dev/kvm.",
            )

        adb.wait_for_boot()

        host.echo("Installing APK...")
        adb.run(["install", "-r", str(workspace.apk)])
        adb.run(["reverse", "tcp:5173", "tcp:5173"], quiet=True)

        adb.ensure_frida_server()

        static = ["--static-bridges", str(workspace.static_bridges)] if workspace.static_bridges.is_file() else []
        if build_agent.main(["--out", str(workspace.agent), *static]) != 0:
            host.die("Error: failed to build Sentry agent")

        device = host.getenv("SENTRY_FRIDA_DEVICE")
        target = ["-D", device] if device else ["-U"]
        host.tee(["frida", *target, "-f", context.package, "-l", str(workspace.agent)], workspace.capture_files)
