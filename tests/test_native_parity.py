"""The bundled agent emits the same events as the legacy two-script load against a mocked Java runtime (FR-004, FR-009)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tests.helpers import LEGACY_DIR, REPO_ROOT, SENTRY_DIR, have_node

HARNESS = REPO_ROOT / "tests" / "tools" / "native_harness.js"


def run_harness(*args: str) -> dict:
    result = subprocess.run(["node", str(HARNESS), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"native harness failed ({args[0]}):\n{result.stderr}")
    return json.loads(result.stdout)


@unittest.skipUnless(have_node(), "node is not installed")
class NativeParity(unittest.TestCase):
    def test_bundle_matches_legacy(self) -> None:
        legacy = run_harness("legacy", str(LEGACY_DIR / "webview.js"), str(LEGACY_DIR / "getenv.js"))
        with tempfile.TemporaryDirectory() as tmp:
            agent = Path(tmp) / "agent.js"
            build = subprocess.run(
                [sys.executable, str(SENTRY_DIR / "core" / "agent" / "build_agent.py"), "--out", str(agent)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            bundled = run_harness("bundle", str(agent))

        types = Counter(json.loads(line)["type"] for line in legacy["events"])
        expected_types = {
            "webview.created", "webview.added", "webview.settings.changed", "webview.client.set",
            "webview.chrome_client.set", "url.loaded", "webview.page.loaded", "permission.requested",
            "permission.grant.called", "permission.deny.called", "bridge.added", "bridge.method.added",
            "bridge.method.called", "js.evaluated", "js.probe",
        }
        self.assertEqual(expected_types - set(types), set(), f"legacy harness missed event types: {types}")
        self.assertEqual(bundled["results"], legacy["results"])
        self.assertEqual(bundled["events"], legacy["events"])


STATIC_ARTIFACT = {
    "schema": 1,
    "status": "completed",
    "registrations": [
        {"name": "AppBridge", "class_name": "com.example.Bridge", "candidate_classes": ["com.example.Bridge"], "methods": []},
    ],
    "bridge_classes": [
        {
            "class_name": "com.example.Bridge",
            "methods": [
                {"name": "getToken", "params": [], "declared_in": "com.example.Bridge"},
                {"name": "ping", "params": ["java.lang.String"], "declared_in": "com.example.Bridge"},
            ],
        },
        {"class_name": "com.example.Hidden", "methods": [{"name": "deleteAll", "params": [], "declared_in": "com.example.Hidden"}]},
    ],
}


@unittest.skipUnless(have_node(), "node is not installed")
class StaticPreInstrumentation(unittest.TestCase):
    def test_static_hooks_log_unregistered_calls_and_keep_dynamic_events(self) -> None:
        legacy = run_harness("legacy", str(LEGACY_DIR / "webview.js"), str(LEGACY_DIR / "getenv.js"))
        with tempfile.TemporaryDirectory() as tmp:
            artifact, agent = Path(tmp) / "static.json", Path(tmp) / "agent.js"
            artifact.write_text(json.dumps(STATIC_ARTIFACT), encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(SENTRY_DIR / "core" / "agent" / "build_agent.py"), "--out", str(agent), "--static-bridges", str(artifact)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            static = run_harness("static", str(agent))

        hidden = [line for line in static["events"] if "com.example.Hidden" in line]
        self.assertEqual([line for line in static["events"] if line not in hidden], legacy["events"])
        (event,) = [json.loads(line) for line in hidden]
        self.assertEqual(event["type"], "bridge.method.called")
        self.assertEqual(event["data"]["className"], "com.example.Hidden")
        self.assertEqual(event["data"]["methodName"], "deleteAll")
        self.assertIsNone(event["data"]["webViewId"])


if __name__ == "__main__":
    unittest.main()
