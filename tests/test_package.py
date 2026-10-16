"""The shared aapt lookup and package parser (FR-014; replaces the shell package.sh)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.host import Host  # noqa: E402
from core.run.package import apk_package_name, find_aapt  # noqa: E402

BADGING = "package: name='com.x' versionCode='1'\nsdkVersion:'21'\nuses-permission: name='a.package.b'\n"


def fake_aapt(path: Path, output: str = BADGING) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\ncat <<'OUT'\n{output}OUT\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class FindAapt(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.missing = str(self.root / "nope" / "aapt")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def host(self, **env: str) -> Host:
        return Host({"PATH": "/usr/bin:/bin", "SENTRY_AAPT_FALLBACKS": self.missing, **env})

    def test_path_first(self) -> None:
        on_path = fake_aapt(self.root / "bin" / "aapt")
        fake_aapt(self.root / "sdk" / "build-tools" / "34.0.0" / "aapt")
        found = find_aapt(self.host(PATH=f"{on_path.parent}:/usr/bin:/bin", ANDROID_HOME=str(self.root / "sdk")))
        self.assertEqual(found, str(on_path))

    def test_newest_sdk_build_tools(self) -> None:
        sdk = self.root / "sdk"
        for version in ("9.0.0", "30.0.3", "34.0.0"):
            fake_aapt(sdk / "build-tools" / version / "aapt")
        self.assertEqual(find_aapt(self.host(ANDROID_HOME=str(sdk))), str(sdk / "build-tools" / "34.0.0" / "aapt"))

    def test_android_sdk_root_when_home_unset(self) -> None:
        sdk = self.root / "sdk-root"
        fake_aapt(sdk / "build-tools" / "33.0.1" / "aapt")
        self.assertEqual(find_aapt(self.host(ANDROID_SDK_ROOT=str(sdk))), str(sdk / "build-tools" / "33.0.1" / "aapt"))

    def test_non_executable_sdk_aapt_ignored(self) -> None:
        sdk = self.root / "sdk"
        fake_aapt(sdk / "build-tools" / "34.0.0" / "aapt").chmod(0o644)
        self.assertIsNone(find_aapt(self.host(ANDROID_HOME=str(sdk))))

    def test_fallback_paths_last(self) -> None:
        fallback = fake_aapt(self.root / "brew" / "aapt")
        (self.root / "empty-sdk" / "build-tools").mkdir(parents=True)
        host = self.host(ANDROID_HOME=str(self.root / "empty-sdk"), SENTRY_AAPT_FALLBACKS=f"{self.missing} {fallback}")
        self.assertEqual(find_aapt(host), str(fallback))

    def test_not_found(self) -> None:
        self.assertIsNone(find_aapt(self.host()))


class ApkPackageName(unittest.TestCase):
    def test_strict_single_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            aapt = fake_aapt(Path(tmp) / "aapt")
            self.assertEqual(apk_package_name(Host({"PATH": "/usr/bin:/bin"}), str(aapt), "some.apk"), "com.x")

    def test_missing_tool_gives_empty_name(self) -> None:
        self.assertEqual(apk_package_name(Host({"PATH": "/usr/bin:/bin"}), "/nonexistent/aapt", "x.apk"), "")


if __name__ == "__main__":
    unittest.main()
