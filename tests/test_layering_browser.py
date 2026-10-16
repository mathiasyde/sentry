"""browser/ runs only inside WebView pages: no Java, Frida or vocabulary references (FR-008, FR-012, SC-007)."""

from __future__ import annotations

import unittest

from tests.helpers import SENTRY_DIR
from tests.layering_helpers import assert_has_header, assert_max_lines, assert_no_pattern, iter_files

BROWSER = SENTRY_DIR / "browser"


class BrowserLayering(unittest.TestCase):
    def setUp(self) -> None:
        self.files = iter_files(BROWSER, [".js"])
        self.assertTrue(self.files, "no browser sources found")

    def test_no_native_or_frida_references(self) -> None:
        assert_no_pattern(self, self.files, r"\bJava\.", "browser code must not use Java")
        assert_no_pattern(self, self.files, r"\bEVENT_TYPE\b", "browser code must not use the event vocabulary")
        assert_no_pattern(self, self.files, r"console\.log\(", "browser code must not print")
        assert_no_pattern(self, self.files, r"\bsend\(", "browser code must not use Frida send()")
        assert_no_pattern(self, self.files, r"\$\{", "browser sources must not contain template literals")

    def test_headers(self) -> None:
        for path in self.files:
            assert_has_header(self, path)

    def test_size(self) -> None:
        assert_max_lines(self, self.files, 430)


if __name__ == "__main__":
    unittest.main()
