"""End-to-end local-mode runs against fake adb/frida: the Python orchestration matches the legacy shell (FR-001, FR-002)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import LEGACY_DIR, LOGS_DIR, REPO_ROOT, SENTRY_DIR

import sys

sys.path.insert(0, str(SENTRY_DIR))

from tests.fakes import install_fake_tools  # noqa: E402

EVENTS = LOGS_DIR / "synthetic" / "full.log"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def make_tree(kind: str, root: Path) -> None:
    """A self-contained checkout: legacy (shell + legacy report.py) or current (launcher + sentry/)."""
    root.mkdir(parents=True)
    if kind == "legacy":
        shutil.copyfile(LEGACY_DIR / "analyse.sh", root / "analyse.sh")
        (root / "sentry").mkdir()
        shutil.copyfile(LEGACY_DIR / "report.py", root / "sentry" / "report.py")
    else:
        shutil.copyfile(REPO_ROOT / "analyse.sh", root / "analyse.sh")
        shutil.copytree(SENTRY_DIR, root / "sentry", ignore=shutil.ignore_patterns("__pycache__", "build"))
    shutil.copyfile(REPO_ROOT / "README.md", root / "app.apk")


def env_for(root: Path, **extra: str) -> dict[str, str]:
    python_dir = os.path.dirname(shutil.which("python3"))
    return {
        "PATH": f"{root / 'fakebin'}:{python_dir}:{SYSTEM_PATH}",
        "SENTRY_RUNNER": "local",
        "SENTRY_FAKE_CALLS": str(root / "calls.log"),
        "SENTRY_FAKE_EVENTS": str(EVENTS),
        **extra,
    }


def analyse_args(kind: str, discover: bool) -> list[str]:
    """Legacy-parity runs switch static discovery off: that is the mode that must match the legacy script (FR-016)."""
    flag = [] if kind == "legacy" or discover else ["--no-discover-bridge-interfaces"]
    return ["sh", "analyse.sh", *flag, "app.apk", "com.example.app"]


def run(kind: str, tmp: Path, discover: bool = False, **extra: str) -> tuple[subprocess.CompletedProcess, Path]:
    root = tmp / kind
    make_tree(kind, root)
    install_fake_tools(root / "fakebin")
    result = subprocess.run(
        analyse_args(kind, discover),
        cwd=root,
        env=env_for(root, **extra),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, root


def interrupted(kind: str, tmp: Path) -> tuple[int, str, Path]:
    root = tmp / kind
    make_tree(kind, root)
    install_fake_tools(root / "fakebin")
    process = subprocess.Popen(
        analyse_args(kind, False),
        cwd=root,
        env=env_for(root, SENTRY_FAKE_HANG="1"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        calls = root / "calls.log"
        if calls.exists() and "frida-ready" in calls.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    time.sleep(0.5)
    os.killpg(process.pid, signal.SIGINT)
    output, _ = process.communicate(timeout=30)
    return process.returncode, output, root


@unittest.skipIf(os.name != "posix", "POSIX shells required")
class LocalSimulation(unittest.TestCase):
    def test_full_run_matches_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy, legacy_root = run("legacy", Path(tmp))
            current, current_root = run("current", Path(tmp))
            self.check_same_run(legacy, legacy_root, current, current_root)

    def check_same_run(self, legacy, legacy_root: Path, current, current_root: Path) -> None:
        self.assertEqual(current.returncode, legacy.returncode)
        self.assertEqual(current.stdout, legacy.stdout)
        for relative in ("target/output.log", "logs/output.log", "target/report.json", "logs/report.md", "target/.env"):
            self.assertEqual(
                (current_root / relative).read_bytes(), (legacy_root / relative).read_bytes(), f"{relative} differs"
            )

        legacy_calls = (legacy_root / "calls.log").read_text(encoding="utf-8").splitlines()
        current_calls = (current_root / "calls.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual([c for c in current_calls if c.startswith("adb")], [c.replace("./target/", "target/") for c in legacy_calls if c.startswith("adb")])
        self.assertIn("frida -U -f com.example.app -l target/agent.js", current_calls)
        self.assertTrue((current_root / "target" / "agent.js").is_file())

    def test_default_discovery_failure_keeps_the_run(self) -> None:
        """app.apk is not a zip here: discovery fails, warns, and the run and report still complete (SC-005)."""
        with tempfile.TemporaryDirectory() as tmp:
            legacy, _ = run("legacy", Path(tmp))
            current, root = run("current", Path(tmp), discover=True)
            artifact = (root / "target" / "static-bridges.json").read_text(encoding="utf-8")
            report = (root / "target" / "report.json").read_text(encoding="utf-8")
        self.assertEqual(current.returncode, legacy.returncode)
        self.assertIn("Warning: static bridge discovery failed: BadZipFile", current.stdout)
        without_warning = [line for line in current.stdout.splitlines(True) if not line.startswith("Warning: static")]
        self.assertEqual("".join(without_warning), legacy.stdout)
        self.assertIn('"status": "failed"', artifact)
        self.assertIn('"static_bridges"', report)

    def test_device_selection_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current, root = run("current", Path(tmp), SENTRY_ADB_SERIAL="emulator-5554", SENTRY_FRIDA_DEVICE="dev-1")
            calls = (root / "calls.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
        self.assertTrue(all(c.startswith("adb -s emulator-5554 ") for c in calls if c.startswith("adb")))
        self.assertIn("frida -D dev-1 -f com.example.app -l target/agent.js", calls)

    def test_ctrl_c_generates_report_and_exits_130(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy_rc, legacy_out, legacy_root = interrupted("legacy", Path(tmp))
            current_rc, current_out, current_root = interrupted("current", Path(tmp))
            legacy_json = (legacy_root / "target" / "report.json").read_bytes()
            current_json = (current_root / "target" / "report.json").read_bytes()

        self.assertEqual(legacy_rc, 130, legacy_out)
        self.assertEqual(current_rc, 130, current_out)
        self.assertEqual(current_json, legacy_json)
        self.assertIn("Generated report:", current_out)


if __name__ == "__main__":
    unittest.main()
