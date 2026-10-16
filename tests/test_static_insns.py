"""core/static instruction widths, payload skipping and operand decoding."""

from __future__ import annotations

import sys
import unittest

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static import insns as I  # noqa: E402
from tests.static_asm import const_string, goto, invoke, invoke_range, return_void, u  # noqa: E402


class Widths(unittest.TestCase):
    def test_widths(self) -> None:
        code = const_string(0, 5) + invoke(0x6E, 7, 1, 2, 0) + u(0x18, 1, 2, 3, 4) + u(0xFA | 0x20 << 8, 1, 0x21, 2)
        self.assertEqual([(off, w) for off, _op, w in I.iter_insns(code)], [(0, 2), (2, 3), (5, 5), (10, 4)])

    def test_payloads_are_skipped(self) -> None:
        packed = u(0x0100, 2, 0, 0, 3, 0, 4, 0)  # ident, size, first_key, 2 targets
        array = u(0x0300, 4, 3, 0, 1, 2, 3, 4, 5, 6)  # ident, width 4, size 3, 6 data units
        code = return_void() + packed + array + return_void()
        self.assertEqual([(off, op) for off, op, _w in I.iter_insns(code)], [(0, 0x0E), (1 + 8 + 10, 0x0E)])


class Decode(unittest.TestCase):
    def test_invoke_register_order(self) -> None:
        insn = I.decode(invoke(0x6E, 9, 1, 2, 3, 4, 5), 0)
        self.assertEqual((insn.ref, insn.regs), (9, (1, 2, 3, 4, 5)))

    def test_invoke_range(self) -> None:
        insn = I.decode(invoke_range(0x74, 9, 20, 3), 0)
        self.assertEqual((insn.ref, insn.regs), (9, (20, 21, 22)))

    def test_const_string_and_branches(self) -> None:
        self.assertEqual(I.decode(const_string(7, 42), 0)[1:4], (0x1A, (7,), 42))
        self.assertEqual(I.decode(return_void() + goto(-1), 1).targets, (0,))

    def test_switch_targets(self) -> None:
        code = u(0x2B | 0 << 8, 4, 0) + return_void() + u(0x0100, 2, 0, 0, 4, 0, 5, 0)
        self.assertEqual(I.decode(code, 0).targets, (4, 5))
        sparse = u(0x2C, 4, 0) + return_void() + u(0x0200, 1, 10, 0, 6, 0)
        self.assertEqual(I.decode(sparse, 0).targets, (6,))

    def test_wide_destination(self) -> None:
        self.assertEqual(I.decode(u(0x16 | 4 << 8, 1), 0).writes, (4, 5))
        self.assertEqual(I.decode(u(0x13 | 4 << 8, 1), 0).writes, (4,))


if __name__ == "__main__":
    unittest.main()
