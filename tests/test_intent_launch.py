"""core/static/intent_launch (am argv synthesis) and core/run/intent_launch (firing them via adb)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.host import Result  # noqa: E402
from core.run.intent_launch import launch_profiled_activities  # noqa: E402
from core.run.workspace import Workspace  # noqa: E402
from core.static.intent_launch import build_am_commands, build_uri, placeholder_for  # noqa: E402
from tests.fakes import FakeHost  # noqa: E402


def activity(**overrides) -> dict:
    base = {
        "class_name": "com.example.app.MainActivity",
        "exported": True,
        "exported_declared": True,
        "intent_filters": [],
        "intent_keys": [],
    }
    return base | overrides


def key(name, accessor, accessor_method) -> dict:
    return {"name": name, "name_status": "resolved", "name_source": {}, "accessor": accessor, "accessor_method": accessor_method}


class Placeholder(unittest.TestCase):
    def test_typed_by_accessor_method(self) -> None:
        self.assertEqual(placeholder_for(key("k", "extra", "getBooleanExtra")), "true")
        self.assertEqual(placeholder_for(key("k", "extra", "getIntExtra")), "1")
        self.assertEqual(placeholder_for(key("k", "extra", "getLongExtra")), "1")
        self.assertEqual(placeholder_for(key("k", "extra", "getStringExtra")), "sentry-probe")
        self.assertEqual(placeholder_for(key("k", "extra", None)), "sentry-probe")


class BuildUri(unittest.TestCase):
    def test_no_scheme_is_none(self) -> None:
        self.assertIsNone(build_uri(None, []))
        self.assertIsNone(build_uri({"host": "open"}, []))

    def test_scheme_host_path_port_and_query(self) -> None:
        data = {"scheme": "myapp", "host": "open", "port": "8080", "pathPrefix": "item"}
        self.assertEqual(build_uri(data, [("id", "1")]), "myapp://open:8080/item?id=1")

    def test_query_values_are_escaped(self) -> None:
        data = {"scheme": "myapp", "host": "open"}
        self.assertEqual(build_uri(data, [("a b", "c&d")]), "myapp://open?a%20b=c%26d")


class BuildAmCommands(unittest.TestCase):
    def test_no_intent_filters_still_launches_the_component(self) -> None:
        (argv,) = build_am_commands("com.example.app", activity())
        self.assertEqual(argv, ["am", "start", "-W", "-n", "com.example.app/com.example.app.MainActivity", "-a", "android.intent.action.VIEW"])

    def test_filter_data_and_non_default_category_become_flags(self) -> None:
        act = activity(
            intent_filters=[
                {
                    "actions": ["android.intent.action.VIEW"],
                    "categories": ["android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"],
                    "data": [{"scheme": "myapp", "host": "open", "pathPrefix": "item"}],
                }
            ]
        )
        (argv,) = build_am_commands("com.example.app", act)
        self.assertEqual(
            argv,
            [
                "am", "start", "-W", "-n", "com.example.app/com.example.app.MainActivity", "-a", "android.intent.action.VIEW",
                "-c", "android.intent.category.BROWSABLE", "-d", "myapp://open/item",
            ],
        )

    def test_extras_and_query_keys_land_in_the_right_place(self) -> None:
        act = activity(
            intent_filters=[{"actions": [], "categories": [], "data": [{"scheme": "myapp", "host": "open"}]}],
            intent_keys=[key("token", "extra", "getStringExtra"), key("id", "query", "getQueryParameter"), key(None, "extra", "getStringExtra")],
        )
        (argv,) = build_am_commands("com.example.app", act)
        self.assertEqual(
            argv,
            [
                "am", "start", "-W", "-n", "com.example.app/com.example.app.MainActivity", "-a", "android.intent.action.VIEW",
                "-d", "myapp://open?id=sentry-probe", "--es", "token", "sentry-probe",
            ],
        )  # the query key lands in the URI, the extra key as --es, the unresolved (name=None) key contributes nothing

    def test_multiple_data_entries_and_filters_are_each_a_command_deduplicated(self) -> None:
        act = activity(
            intent_filters=[
                {"actions": [], "categories": [], "data": [{"scheme": "a", "host": "h"}, {"scheme": "b", "host": "h"}]},
                {"actions": [], "categories": [], "data": [{"scheme": "a", "host": "h"}]},  # duplicate of the first filter's first data
            ]
        )
        commands = build_am_commands("com.example.app", act)
        self.assertEqual(len(commands), 2)
        self.assertEqual({c[-1] for c in commands}, {"a://h", "b://h"})


class LaunchProfiledActivities(unittest.TestCase):
    def workspace(self, tmp: Path) -> Workspace:
        ws = Workspace(tmp)
        ws.target.mkdir(parents=True, exist_ok=True)
        return ws

    def write(self, ws: Workspace, payload: dict) -> None:
        ws.intent_profile.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_artifact_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            host = FakeHost()
            launch_profiled_activities(host, host, ws, "com.example.app", False)
        self.assertEqual(host.calls, [])

    def test_failed_or_empty_artifact_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            self.write(ws, {"status": "failed", "activities": []})
            host = FakeHost()
            launch_profiled_activities(host, host, ws, "com.example.app", False)
        self.assertEqual(host.calls, [])

    def test_fires_one_am_start_per_command_after_a_delay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            self.write(ws, {"status": "completed", "activities": [activity()]})
            host = FakeHost()
            launch_profiled_activities(host, host, ws, "com.example.app", False)
        self.assertEqual(host.calls[0], ("sleep", 3.0))
        self.assertEqual(
            host.calls[1],
            ("run", ["shell", "am start -W -n com.example.app/com.example.app.MainActivity -a android.intent.action.VIEW"], {}),
        )

    def test_verbose_echoes_a_line_per_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            self.write(ws, {"status": "completed", "activities": [activity()]})
            host = FakeHost()
            buf = []
            host.echo = lambda *lines, err=False: buf.extend(lines)  # type: ignore[method-assign]
            launch_profiled_activities(host, host, ws, "com.example.app", True)
        self.assertEqual(len(buf), 1)
        self.assertTrue(buf[0].startswith("am start -> com.example.app.MainActivity (ok): "))

    def test_retries_a_failing_launch_with_backoff_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            self.write(ws, {"status": "completed", "activities": [activity()]})
            attempts = {"n": 0}

            def respond(cmd):
                attempts["n"] += 1
                return Result(0 if attempts["n"] >= 3 else 1)

            host = FakeHost(respond=respond)
            launch_profiled_activities(host, host, ws, "com.example.app", False)
        runs = [c for c in host.calls if c[0] == "run"]
        sleeps = [c for c in host.calls if c[0] == "sleep"]
        self.assertEqual(len(runs), 3)
        self.assertEqual(sleeps, [("sleep", 3.0), ("sleep", 1.5), ("sleep", 3.0)])

    def test_gives_up_after_max_attempts_and_says_so_when_verbose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(Path(tmp))
            self.write(ws, {"status": "completed", "activities": [activity()]})
            host = FakeHost(respond=lambda cmd: Result(1))
            buf = []
            host.echo = lambda *lines, err=False: buf.extend(lines)  # type: ignore[method-assign]
            launch_profiled_activities(host, host, ws, "com.example.app", True)
        runs = [c for c in host.calls if c[0] == "run"]
        self.assertEqual(len(runs), 3)  # MAX_ATTEMPTS, no more
        self.assertEqual(len(buf), 1)
        self.assertTrue(buf[0].startswith("am start -> com.example.app.MainActivity (exit 1, gave up after 3 attempts): "))


if __name__ == "__main__":
    unittest.main()
