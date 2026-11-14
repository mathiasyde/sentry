"""core/run: fire `am start` for every WebView-touching activity the intent-data profile found.

Runs concurrently with the live Frida session: core/runners/local.py starts it in a background
thread, right before the blocking frida/tee call, because the app has to already be running and
hooked for a launch to land in an instrumented process. Best-effort only - a missing or failed
profile just means nothing to launch, and no exception from here is allowed to reach the run.

A failed `am start` (the activity manager busy, the app still mid-launch, a transient adb hiccup) is
retried with backoff rather than given up on after one try.
"""

from __future__ import annotations

import json
import shlex
from typing import Any

from core.host import Host, Result
from core.run.workspace import Workspace
from core.static.intent_launch import build_am_commands

DELAY_SECONDS = 3.0
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.5
BACKOFF_MULTIPLIER = 2.0


def run_with_retry(host: Host, adb: Any, shell_command: str) -> tuple[Result, int]:
    """Retry a failing `adb shell <command>` with exponential backoff; return (last result, attempts used)."""
    delay = BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = adb.run(["shell", shell_command])
        if result.returncode == 0 or attempt == MAX_ATTEMPTS:
            return result, attempt
        host.sleep(delay)
        delay *= BACKOFF_MULTIPLIER
    return result, MAX_ATTEMPTS  # pragma: no cover - loop above always returns


def launch_profiled_activities(host: Host, adb: Any, workspace: Workspace, package: str, verbose: bool) -> None:
    try:
        data = json.loads(workspace.intent_profile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if data.get("status") != "completed":
        return
    commands = [
        (activity["class_name"], argv)
        for activity in data.get("activities") or []
        for argv in build_am_commands(package, activity)
    ]
    if not commands:
        return

    host.sleep(DELAY_SECONDS)
    for class_name, argv in commands:
        shell_command = " ".join(shlex.quote(token) for token in argv)
        result, attempts = run_with_retry(host, adb, shell_command)
        if verbose:
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}, gave up"
            tries = "" if attempts == 1 else f" after {attempts} attempts"
            host.echo(f"am start -> {class_name} ({status}{tries}): {shell_command}")
