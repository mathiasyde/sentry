"""analyse.sh and the benchmark runner keep their user-facing contract (FR-001, FR-006)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import LEGACY_DIR, REPO_ROOT

OPTIONS_LINE = "Options: --[no-]discover-bridge-interfaces[=true|false]  static JavaScript bridge discovery (default: true)"

SCENARIOS = {
    "no_args": ([], {}),
    "missing_file": (["missing.apk", "pkg"], {}),
    "bad_runner": (["README.md", "pkg"], {"SENTRY_RUNNER": "bogus"}),
}


def run_analyse(cwd: Path, args: list[str], extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **extra_env}
    return subprocess.run(["sh", "analyse.sh", *args], cwd=cwd, env=env, capture_output=True, text=True)


class AnalyseContract(unittest.TestCase):
    def test_no_args(self) -> None:
        result = run_analyse(REPO_ROOT, *SCENARIOS["no_args"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Sentry - version alpha", result.stdout)
        self.assertIn("Usage: analyse.sh <apk> [<apk-package>]\n" + OPTIONS_LINE + "\n", result.stdout)

    def test_missing_file(self) -> None:
        result = run_analyse(REPO_ROOT, *SCENARIOS["missing_file"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("File not found: missing.apk", result.stdout)

    def test_bad_runner_has_no_side_effects(self) -> None:
        env_file = REPO_ROOT / "target" / ".env"
        before = env_file.read_bytes() if env_file.exists() else None
        result = run_analyse(REPO_ROOT, *SCENARIOS["bad_runner"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: invalid SENTRY_RUNNER 'bogus' (expected auto, docker, or local)", result.stdout)
        after = env_file.read_bytes() if env_file.exists() else None
        self.assertEqual(before, after, "invalid runner must not prepare the workspace")

    def test_matches_legacy_output(self) -> None:
        for name, (args, env) in SCENARIOS.items():
            with self.subTest(scenario=name), tempfile.TemporaryDirectory() as tmp:
                legacy_cwd = Path(tmp)
                shutil.copyfile(LEGACY_DIR / "analyse.sh", legacy_cwd / "analyse.sh")
                shutil.copyfile(REPO_ROOT / "README.md", legacy_cwd / "README.md")
                legacy = run_analyse(legacy_cwd, args, env)
                current = run_analyse(REPO_ROOT, args, env)
                # Intentional deviation (specs/002 contracts/cli-analyse-option.md): usage gains an Options line.
                expected = legacy.stdout + OPTIONS_LINE + "\n" if name == "no_args" else legacy.stdout
                self.assertEqual(current.stdout, expected)
                self.assertEqual(current.returncode, legacy.returncode)


    def test_invalid_discovery_value(self) -> None:
        env_file = REPO_ROOT / "target" / ".env"
        before = env_file.read_bytes() if env_file.exists() else None
        result = run_analyse(REPO_ROOT, ["--discover-bridge-interfaces=maybe", "README.md", "pkg"], {})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: invalid value 'maybe' for --discover-bridge-interfaces (expected true or false)", result.stdout)
        after = env_file.read_bytes() if env_file.exists() else None
        self.assertEqual(before, after, "an invalid option must not prepare the workspace")


class BenchmarkContract(unittest.TestCase):
    def test_help(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/run-benchmarks-linux.sh", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("Usage: run-benchmarks-linux.sh [benchmark-dir]"), result.stdout)

    def test_help_matches_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            shutil.copyfile(LEGACY_DIR / "run-benchmarks-linux.sh", scripts / "run-benchmarks-linux.sh")
            legacy = subprocess.run(["bash", "scripts/run-benchmarks-linux.sh", "--help"], cwd=tmp, capture_output=True, text=True)
        current = subprocess.run(["bash", "scripts/run-benchmarks-linux.sh", "--help"], cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(current.stdout, legacy.stdout)
        self.assertEqual(current.returncode, legacy.returncode)


if __name__ == "__main__":
    unittest.main()
