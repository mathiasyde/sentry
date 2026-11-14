"""Runner strategies, runner selection and the container entry points, driven through a recording host."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.host import Result  # noqa: E402
from core.run.workspace import Workspace  # noqa: E402
from core.runners import RunContext, select_runner  # noqa: E402
from core.runners.container import entry, frida_server  # noqa: E402
from core.runners.docker import DockerRunner  # noqa: E402
from core.runners.local import LocalRunner  # noqa: E402
from tests.fakes import FakeHost  # noqa: E402


def capture(fn, *args):
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out):
        try:
            fn(*args)
        except SystemExit as exit_:
            code = exit_.code
    return out.getvalue(), code


def context(host: FakeHost, kvm: bool = True) -> RunContext:
    return RunContext(host, Workspace(Path(".")), "app.apk", "com.example.app", kvm)


class SelectRunner(unittest.TestCase):
    def test_auto(self) -> None:
        self.assertIsInstance(select_runner("auto", FakeHost(linux=True), True), DockerRunner)
        self.assertIsInstance(select_runner("auto", FakeHost(linux=True), False), LocalRunner)
        self.assertIsInstance(select_runner("auto", FakeHost(linux=False), True), LocalRunner)

    def test_explicit_and_invalid(self) -> None:
        self.assertIsInstance(select_runner("docker", FakeHost(), False), DockerRunner)
        self.assertIsInstance(select_runner("local", FakeHost(), True), LocalRunner)
        out, code = capture(select_runner, "bogus", FakeHost(), True)
        self.assertEqual(code, 1)
        self.assertEqual(out, "Error: invalid SENTRY_RUNNER 'bogus' (expected auto, docker, or local)\n")


class DockerRunnerTests(unittest.TestCase):
    def test_commands(self) -> None:
        host = FakeHost()
        out, code = capture(DockerRunner().run, context(host))
        self.assertIsNone(code)
        self.assertEqual(
            host.commands_run(),
            [
                ["docker", "compose", "down"],
                ["docker", "compose", "up", "-d", "emulator", "run-frida-server", "sentry"],
                ["docker", "logs", "-f", "sentry"],
            ],
        )
        self.assertEqual(host.calls[-1][2], ["target/output.log", "logs/output.log"])

    def test_requires_docker_and_kvm(self) -> None:
        out, code = capture(DockerRunner().run, context(FakeHost(commands={"python3"})))
        self.assertEqual((out, code), ("Error: docker is not installed\n", 1))
        out, code = capture(DockerRunner().run, context(FakeHost(), kvm=False))
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("Error: Docker emulator mode requires /dev/kvm.\n"))

    def test_preflight_needs_compose_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                out, code = capture(DockerRunner().preflight, context(FakeHost()))
            finally:
                os.chdir(cwd)
        self.assertEqual((out, code), ("Error: docker-compose.yml not found\n", 1))


class LocalRunnerTests(unittest.TestCase):
    def test_boot_timeout(self) -> None:
        def respond(cmd):
            return Result(0, "0\n") if "getprop" in cmd else Result(0)

        host = FakeHost(env={"PATH": "/fake", "SENTRY_BOOT_TIMEOUT": "4"}, respond=respond)
        out, code = capture(LocalRunner().run, context(host))
        self.assertEqual(code, 1)
        self.assertIn("Error: Android emulator did not finish booting within 4s\n", out)
        self.assertEqual([c for c in host.calls if c[0] == "sleep"], [("sleep", 2), ("sleep", 2)])

    def test_missing_frida_server(self) -> None:
        def respond(cmd):
            if "getprop" in cmd:
                return Result(0, "1\r\n")
            return Result(1) if cmd[-1].startswith("test -x") else Result(0)

        out, code = capture(LocalRunner().run, context(FakeHost(respond=respond)))
        self.assertEqual(code, 1)
        self.assertIn("Error: frida-server was not found at /data/local/tmp/frida-server on the emulator.\n", out)

    def test_no_device(self) -> None:
        host = FakeHost(respond=lambda cmd: Result(1) if cmd[-1] == "get-state" else Result(0))
        out, code = capture(LocalRunner().run, context(host, kvm=True))
        self.assertEqual(code, 1)
        self.assertEqual(out, "Using local emulator mode\nError: no Android emulator/device is visible to adb.\n"
                         "Start an emulator first, or set SENTRY_RUNNER=docker on a Linux host with /dev/kvm.\n")


class ContainerEntryPoints(unittest.TestCase):
    def test_sentry_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("APP_PACKAGE=com.example.app\n", encoding="utf-8")
            host = FakeHost(respond=lambda cmd: Result(3 if cmd[0] == "frida" else 0))
            code = entry.main(host, env_file)
        self.assertEqual(code, 3)
        self.assertEqual(
            host.commands_run(),
            [
                ["adb", "connect", "emulator:5555"],
                ["adb", "forward", "tcp:27042", "tcp:27042"],
                ["adb", "reverse", "tcp:5173", "tcp:5173"],
                ["frida", "-H", "127.0.0.1:27042", "-f", "com.example.app", "-l", "/sentry/build/agent.js"],
            ],
        )

    def test_sentry_entry_launches_profiled_activities_concurrently(self) -> None:
        class SynchronousThread:
            """Runs the target immediately instead of in a background thread, so the test is deterministic."""

            def __init__(self, target, args=(), daemon=False) -> None:
                self.target, self.args = target, args

            def start(self) -> None:
                self.target(*self.args)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target").mkdir()
            env_file = root / "target" / ".env"
            env_file.write_text("APP_PACKAGE=com.example.app\nSENTRY_VERBOSE=true\n", encoding="utf-8")
            profile = {
                "status": "completed",
                "activities": [
                    {"class_name": "com.example.app.MainActivity", "exported": True, "exported_declared": True,
                     "intent_filters": [], "intent_keys": []}
                ],
            }
            (root / "target" / "intent-data-profile.json").write_text(json.dumps(profile), encoding="utf-8")
            host = FakeHost(respond=lambda cmd: Result(3 if cmd[0] == "frida" else 0))
            with (
                mock.patch("core.runners.container.entry.threading.Thread", SynchronousThread),
                mock.patch("core.runners.container.entry.WORKSPACE_ROOT", root),
            ):
                code = entry.main(host, env_file)
        self.assertEqual(code, 3)
        shell_calls = [c for c in host.commands_run() if c[:2] == ["adb", "shell"]]
        self.assertEqual(len(shell_calls), 1)
        self.assertIn("am start -W -n com.example.app/com.example.app.MainActivity", shell_calls[0][2])

    def test_entry_stops_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("APP_PACKAGE=x\n", encoding="utf-8")
            host = FakeHost(respond=lambda cmd: Result(5 if cmd[1] == "forward" else 0))
            with self.assertRaises(SystemExit) as raised:
                entry.main(host, env_file)
        self.assertEqual(raised.exception.code, 5)
        self.assertEqual(len(host.commands_run()), 2)

    def test_frida_server_container(self) -> None:
        boots = iter(["0\n", "1\r\n"])

        def respond(cmd):
            return Result(0, next(boots)) if "getprop" in cmd else Result(0)

        env = {"ADB_HOST": "emulator", "ADB_PORT": "5555", "FRIDA_SERVER": "/data/local/tmp/frida-server",
               "TARGET_APK": "/target/app.apk", "ADB_ROOT": "true"}
        host = FakeHost(env=env, respond=respond)
        out, code = capture(frida_server.main, host)
        self.assertEqual(out, "Connecting to ADB (emulator:5555)\nWaiting for boot completion...\nInstalling APK...\n"
                              "Pushing frida-server...\nStarting frida-server...\n")
        self.assertEqual(
            [c for c in host.calls if c[0] != "run" or "getprop" not in c[1]],
            [
                ("sleep", 20),
                ("run", ["adb", "connect", "emulator:5555"], {}),
                ("sleep", 2),
                ("run", ["adb", "root"], {}),
                ("run", ["adb", "install", "-r", "/target/app.apk"], {}),
                ("run", ["adb", "push", "frida-server", "/data/local/tmp/frida-server"], {}),
                ("run", ["adb", "shell", "chmod 755 /data/local/tmp/frida-server"], {}),
                ("run", ["adb", "shell", "/data/local/tmp/frida-server &"], {}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
