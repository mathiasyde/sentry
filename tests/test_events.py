"""The event vocabulary must equal the legacy EVENT_TYPE object, including key order (FR-004, FR-011)."""

from __future__ import annotations

import json
import re
import sys
import unittest

from tests.helpers import LEGACY_DIR, SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.events import ALL, EVENT_TYPES, EventType  # noqa: E402


def legacy_event_types() -> dict[str, str]:
    source = (LEGACY_DIR / "webview.js").read_text(encoding="utf-8")
    block = re.search(r"const EVENT_TYPE = Object\.freeze\(\{(.*?)\}\);", source, re.S).group(1)
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block))


class EventVocabulary(unittest.TestCase):
    def test_matches_legacy_in_order(self) -> None:
        json_types = json.loads((SENTRY_DIR / "core" / "events" / "event_types.json").read_text(encoding="utf-8"))
        legacy = legacy_event_types()
        self.assertEqual(list(json_types.items()), list(legacy.items()))
        self.assertEqual(list(EVENT_TYPES.items()), list(legacy.items()))

    def test_python_constants(self) -> None:
        for name, value in EVENT_TYPES.items():
            self.assertEqual(getattr(EventType, name), value)
        self.assertEqual(ALL, tuple(EVENT_TYPES.values()))


if __name__ == "__main__":
    unittest.main()
