"""Shared paths and runners for the Sentry test suite."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTRY_DIR = REPO_ROOT / "sentry"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
LOGS_DIR = FIXTURES / "logs"
EXPECTED_DIR = FIXTURES / "expected"
LEGACY_DIR = FIXTURES / "legacy"


def case_name(log_path: Path) -> str:
    relative = Path(log_path).resolve().relative_to(LOGS_DIR).with_suffix("")
    return relative.as_posix().replace("/", "__")


def case_args(log_path: Path) -> list[str]:
    args_file = Path(log_path).with_suffix(".args")
    if not args_file.exists():
        return []
    return [line for line in args_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_logs() -> list[Path]:
    return sorted(LOGS_DIR.rglob("*.log"))


def run_report(script_path: Path, log_path: Path, out_dir: Path) -> subprocess.CompletedProcess:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
            str(log_path),
            "--json",
            str(out_dir / "report.json"),
            "--markdown",
            str(out_dir / "report.md"),
            *case_args(log_path),
        ],
        capture_output=True,
        text=True,
    )


def normalize_stdout(stdout: str, out_dir: Path) -> str:
    out_dir = Path(out_dir)
    return (
        stdout.replace(str(out_dir / "report.json"), "<JSON>")
        .replace(str(out_dir / "report.md"), "<MD>")
    )


def have_node() -> bool:
    return shutil.which("node") is not None
