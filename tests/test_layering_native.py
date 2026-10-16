"""native/ intercepts Android APIs only: no page-side code, one module per hook family (FR-009, FR-012, SC-007)."""

from __future__ import annotations

import unittest

from tests.helpers import SENTRY_DIR
from tests.layering_helpers import assert_has_header, assert_max_lines, assert_no_pattern, iter_files

NATIVE = SENTRY_DIR / "native"
EXPECTED = {
    "registry.js",
    "browser_delivery.js",
    "webview_lifecycle.js",
    "webview_settings.js",
    "webview_clients.js",
    "javascript_bridge.js",
    "javascript_evaluation.js",
    "static_bridges.js",
    "permissions.js",
    "environment.js",
    "main.js",
}


class NativeLayering(unittest.TestCase):
    def setUp(self) -> None:
        self.files = iter_files(NATIVE, [".js"])

    def test_module_set(self) -> None:
        self.assertEqual({path.name for path in self.files}, EXPECTED)
        self.assertFalse((NATIVE / "webview_hooks.js").exists())

    def test_no_page_side_code(self) -> None:
        assert_no_pattern(self, self.files, r"\bwindow[.\[]", "page-side code belongs in browser/")
        assert_no_pattern(self, self.files, r"\bdocument\.", "page-side code belongs in browser/")

    def test_headers(self) -> None:
        for path in self.files:
            assert_has_header(self, path)

    def test_size(self) -> None:
        assert_max_lines(self, self.files, 430)


if __name__ == "__main__":
    unittest.main()
