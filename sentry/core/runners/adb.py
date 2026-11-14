"""core/runners: adb adapter for the local runner (SENTRY_ADB_SERIAL, boot wait, frida-server startup)."""

from __future__ import annotations

from core.host import CAPTURE, DISCARD, Host, Result


class Adb:
    def __init__(self, host: Host) -> None:
        self.host = host
        self.serial = host.getenv("SENTRY_ADB_SERIAL")

    def command(self, args: list[str]) -> list[str]:
        return ["adb", "-s", self.serial, *args] if self.serial else ["adb", *args]

    def run(self, args: list[str], **kwargs) -> Result:
        return self.host.run(self.command(args), **kwargs)

    def wait_for_boot(self) -> None:
        timeout = self.host.getenv("SENTRY_BOOT_TIMEOUT") or "120"
        try:
            remaining = int(timeout)
        except ValueError:  # the shell version skipped both checks on a non-integer timeout
            return

        while remaining > 0:
            booted = self.run(["shell", "getprop", "sys.boot_completed"], stdout=CAPTURE, stderr=DISCARD).stdout
            if booted.replace("\r", "").rstrip("\n") == "1":
                break
            self.host.sleep(2)
            remaining -= 2

        if remaining <= 0:
            self.host.die(f"Error: Android emulator did not finish booting within {timeout}s")

    def ensure_frida_server(self) -> None:
        server = self.host.getenv("SENTRY_FRIDA_SERVER") or "/data/local/tmp/frida-server"
        if self.run(["shell", f"test -x '{server}'"], quiet=True).returncode != 0:
            self.host.die(
                f"Error: frida-server was not found at {server} on the emulator.",
                "Install it first, or set SENTRY_FRIDA_SERVER to the correct device path.",
            )

        if self.run(["shell", f"pgrep -f '{server}' >/dev/null 2>&1"]).returncode != 0:
            self.host.echo("Starting frida-server...")
            self.run(["shell", f"{server} >/dev/null 2>&1 &"])
            self.host.sleep(2)
