"""core/run: the one shared aapt lookup and APK package-name parser (used by analyse.sh and the benchmark runner).

Lookup order: PATH, then the newest $ANDROID_HOME (or $ANDROID_SDK_ROOT) build-tools/*/aapt, then the fallback paths.
SENTRY_AAPT_FALLBACKS overrides the fallback paths; it is internal and used only by tests.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.host import CAPTURE, Host

DEFAULT_FALLBACKS = "/opt/homebrew/bin/aapt /usr/local/bin/aapt"
PACKAGE_RE = re.compile(r"^package: name='([^']*)'")


def version_key(path: Path) -> list:
    """Order like `sort -V`: digit runs compare as numbers."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(path))]


def sdk_aapt(build_tools: Path) -> str | None:
    candidates = [build_tools / "aapt", *build_tools.glob("*/aapt")]
    executables = [
        path
        for path in candidates
        if not path.is_symlink() and path.is_file() and os.stat(path).st_mode & 0o111 == 0o111
    ]
    return str(max(executables, key=version_key)) if executables else None


def find_aapt(host: Host) -> str | None:
    on_path = host.which("aapt")
    if on_path:
        return on_path

    sdk_root = host.getenv("ANDROID_HOME") or host.getenv("ANDROID_SDK_ROOT")
    if sdk_root and (Path(sdk_root) / "build-tools").is_dir():
        found = sdk_aapt(Path(sdk_root) / "build-tools")
        if found:
            return found

    for candidate in (host.getenv("SENTRY_AAPT_FALLBACKS") or DEFAULT_FALLBACKS).split():
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def apk_package_name(host: Host, aapt: str, apk: str) -> str:
    output = host.run([aapt, "dump", "badging", apk], stdout=CAPTURE).stdout
    for line in output.splitlines():
        match = PACKAGE_RE.match(line)
        if match:
            return match.group(1)
    return ""
