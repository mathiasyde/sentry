"""core: Host facade over the operating system (environment, PATH, platform, processes, tee pipelines).

Orchestration, runners and the benchmark runner never call subprocess or os directly; they go through a Host,
so tests can substitute a fake host and assert the exact commands that would run.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Sequence

CAPTURE = subprocess.PIPE
DISCARD = subprocess.DEVNULL
MERGE = subprocess.STDOUT


@dataclass
class Result:
    returncode: int
    stdout: str = ""


class Host:
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self.env = dict(os.environ if env is None else env)

    # --- environment ------------------------------------------------------------------------
    def getenv(self, name: str, default: str = "") -> str:
        return self.env.get(name, default)

    def which(self, name: str) -> str | None:
        return shutil.which(name, path=self.env.get("PATH", os.defpath))

    def is_linux(self) -> bool:
        return platform.system() == "Linux"

    def has_kvm(self) -> bool:
        try:
            return stat.S_ISCHR(os.stat("/dev/kvm").st_mode)
        except OSError:
            return False

    # --- output -----------------------------------------------------------------------------
    def echo(self, *lines: str, err: bool = False) -> None:
        stream = sys.stderr if err else sys.stdout
        for line in lines:
            print(line, file=stream, flush=True)

    def die(self, *lines: str, code: int = 1, err: bool = False) -> None:
        """Print the lines, then exit like a failing shell script (exit handlers still run)."""
        self.echo(*lines, err=err)
        raise SystemExit(code)

    # --- processes --------------------------------------------------------------------------
    def run(
        self,
        cmd: Sequence[str],
        *,
        stdout: int | IO | None = None,
        stderr: int | None = None,
        quiet: bool = False,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        """Run a command; stdio is inherited unless redirected. quiet discards both streams (`>/dev/null 2>&1`)."""
        if quiet:
            stdout, stderr = DISCARD, DISCARD
        sys.stdout.flush()
        try:
            completed = subprocess.run(
                list(cmd),
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                env={**self.env, **(env or {})},
                text=stdout is CAPTURE,
            )
        except FileNotFoundError:
            return Result(127)
        return Result(completed.returncode, completed.stdout if stdout is CAPTURE else "")

    def run_checked(self, cmd: Sequence[str]) -> Result:
        """Like a command under `set -e`: exit with the command's status if it fails."""
        result = self.run(cmd)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
        return result

    def tee(self, cmd: Sequence[str], files: Sequence[Path]) -> None:
        """`cmd | tee file...`: stream the command's stdout to our stdout and every file; exit status ignored."""
        sys.stdout.flush()
        handles = [open(path, "wb") for path in files]
        process = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, env=self.env)
        try:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read1(65536)
                if not chunk:
                    break
                for handle in (sys.stdout.buffer, *handles):
                    handle.write(chunk)
                    handle.flush()
            process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            for handle in handles:
                handle.close()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def require_commands(host: Host, *names: str, err: bool = False) -> None:
    """Report every missing command, then exit 1 if any was missing."""
    missing = [name for name in names if host.which(name) is None]
    for name in missing:
        host.echo(f"Error: {name} is not installed", err=err)
    if missing:
        raise SystemExit(1)
