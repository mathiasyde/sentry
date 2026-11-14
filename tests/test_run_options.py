"""analyse.sh option parsing: --[no-]discover-bridge-interfaces[=<bool>], --[no-]verbose[=<bool>]."""

from __future__ import annotations

import sys
import unittest

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.run.options import OptionError, parse_args  # noqa: E402


class ParseArgs(unittest.TestCase):
    def test_default_is_discover_on_verbose_off(self) -> None:
        self.assertEqual(parse_args(["a.apk", "pkg"]), (["a.apk", "pkg"], True, False))
        self.assertEqual(parse_args([]), ([], True, False))

    def test_true_and_false_values(self) -> None:
        for value in ("true", "YES", "on", "1"):
            self.assertTrue(parse_args([f"--discover-bridge-interfaces={value}"])[1], value)
        for value in ("false", "No", "off", "0"):
            self.assertFalse(parse_args([f"--discover-bridge-interfaces={value}"])[1], value)
        self.assertTrue(parse_args(["--discover-bridge-interfaces"])[1])
        self.assertFalse(parse_args(["--no-discover-bridge-interfaces"])[1])

    def test_last_option_wins(self) -> None:
        self.assertFalse(parse_args(["--discover-bridge-interfaces", "--no-discover-bridge-interfaces"])[1])
        self.assertTrue(parse_args(["--no-discover-bridge-interfaces", "--discover-bridge-interfaces=on"])[1])

    def test_position_does_not_matter(self) -> None:
        for argv in (
            ["--no-discover-bridge-interfaces", "a.apk", "pkg"],
            ["a.apk", "--no-discover-bridge-interfaces", "pkg"],
            ["a.apk", "pkg", "--no-discover-bridge-interfaces"],
        ):
            self.assertEqual(parse_args(argv), (["a.apk", "pkg"], False, False))

    def test_other_dashed_arguments_stay_positional(self) -> None:
        self.assertEqual(parse_args(["--foo", "a.apk"]), (["--foo", "a.apk"], True, False))

    def test_invalid_values(self) -> None:
        for value in ("maybe", ""):
            with self.assertRaises(OptionError) as caught:
                parse_args([f"--discover-bridge-interfaces={value}", "a.apk"])
            self.assertEqual(
                str(caught.exception), f"invalid value '{value}' for --discover-bridge-interfaces (expected true or false)"
            )
            with self.assertRaises(OptionError) as caught:
                parse_args([f"--verbose={value}", "a.apk"])
            self.assertEqual(str(caught.exception), f"invalid value '{value}' for --verbose (expected true or false)")

    def test_verbose_true_and_false_values(self) -> None:
        for value in ("true", "YES", "on", "1"):
            self.assertTrue(parse_args([f"--verbose={value}"])[2], value)
        for value in ("false", "No", "off", "0"):
            self.assertFalse(parse_args([f"--verbose={value}"])[2], value)
        self.assertTrue(parse_args(["--verbose"])[2])
        self.assertFalse(parse_args(["--no-verbose"])[2])

    def test_verbose_last_option_wins_and_is_independent_of_discover(self) -> None:
        self.assertEqual(parse_args(["--verbose", "--no-discover-bridge-interfaces", "a.apk"]), (["a.apk"], False, True))
        self.assertEqual(parse_args(["--verbose", "--no-verbose"])[2], False)


if __name__ == "__main__":
    unittest.main()
