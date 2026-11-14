"""core/runners/container: entry point of the run-frida-server container: installs the APK and starts frida-server."""

from __future__ import annotations

from core.host import CAPTURE, DISCARD, Host


def booted(host: Host) -> bool:
    output = host.run(["adb", "shell", "getprop", "sys.boot_completed"], stdout=CAPTURE, stderr=DISCARD).stdout
    return output.replace("\r", "").rstrip("\n") == "1"


def main(host: Host | None = None) -> int:
    host = host or Host()
    adb_host, adb_port = host.env["ADB_HOST"], host.env["ADB_PORT"]
    server, apk = host.env["FRIDA_SERVER"], host.env["TARGET_APK"]

    host.sleep(20)  # FIXME: race condition fix
    host.echo(f"Connecting to ADB ({adb_host}:{adb_port})")
    host.run_checked(["adb", "connect", f"{adb_host}:{adb_port}"])

    host.echo("Waiting for boot completion...")
    while not booted(host):
        host.sleep(2)

    if host.getenv("ADB_ROOT", "false") == "true":
        host.run_checked(["adb", "root"])

    host.echo("Installing APK...")
    host.run_checked(["adb", "install", "-r", apk])

    host.echo("Pushing frida-server...")
    host.run_checked(["adb", "push", "frida-server", server])
    host.run_checked(["adb", "shell", f"chmod 755 {server}"])

    host.echo("Starting frida-server...")
    return host.run(["adb", "shell", f"{server} &"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
