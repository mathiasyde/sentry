"""core/static dataflow: resolving the name and object arguments of bridge call sites."""

from __future__ import annotations

import sys
import unittest

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static.dataflow import ADD, REMOVE, TOP, MethodInfo, analyze_method  # noqa: E402
from tests.static_asm import (  # noqa: E402
    ADD_IDX, REMOVE_IDX, Code, FakeResolver, const_string, goto, if_eqz, invoke, invoke_range,
    move_object_from16, move_result_object, new_instance, return_void, sget_object,
)

BRIDGE = "Lcom/x/Bridge;"
STATIC = MethodInfo("Lcom/x/Main;", True, ())
RESOLVER = FakeResolver(
    strings={i: name for i, name in enumerate("ABCDEFGHIJ")},
    types={0: BRIDGE},
    fields={0: ("Lcom/x/Cfg;", "Ljava/lang/String;", "NAME"), 1: ("Lcom/x/Cfg;", "Ljava/lang/String;", "OTHER")},
    statics={0: "Const"},
    methods={5: ("Lcom/x/Cfg;", "bridgeName", ("Ljava/lang/String;", ()))},
)


def analyze(insns: bytes, registers: int = 4, ins: int = 0, info: MethodInfo = STATIC, handlers=None):
    return analyze_method(Code(registers, ins, insns, [], handlers or {}), info, RESOLVER)


class Arguments(unittest.TestCase):
    def test_const_string_and_new_instance(self) -> None:
        (fact,) = analyze(const_string(0, 0) + new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0) + return_void())
        self.assertEqual(fact.kind, ADD)
        self.assertEqual(fact.name_values, {("str", "A", None)})
        self.assertEqual(fact.object_values, {("new", BRIDGE)})

    def test_branches_give_both_names(self) -> None:
        code = (
            if_eqz(3, 7)              # 0: if v3 == 0 goto 7
            + const_string(0, 0)      # 2: "A"
            + new_instance(1, 0)      # 4
            + goto(4)                 # 6: goto 10
            + const_string(0, 1)      # 7: "B"
            + u_nop()                 # 9
            + new_instance(1, 0)      # 10
            + invoke(0x6E, ADD_IDX, 2, 1, 0)
            + return_void()
        )
        (fact,) = analyze(code)
        self.assertEqual({v[1] for v in fact.name_values}, {"A", "B"})

    def test_method_result_is_recorded(self) -> None:
        (fact,) = analyze(invoke(0x71, 5) + move_result_object(0) + new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0))
        self.assertEqual(fact.name_values, {("result", "com.x.Cfg.bridgeName()", "Ljava/lang/String;")})

    def test_static_field_constant(self) -> None:
        (fact,) = analyze(sget_object(0, 0) + new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0))
        self.assertEqual(fact.name_values, {("str", "Const", "com.x.Cfg.NAME")})
        (fact,) = analyze(sget_object(0, 1) + new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0))
        self.assertEqual(fact.name_values, {("field", "com.x.Cfg.OTHER", "Ljava/lang/String;")})

    def test_this_and_parameters(self) -> None:
        info = MethodInfo("Lcom/x/Main;", False, ("Ljava/lang/Object;", "Ljava/lang/String;"))
        (fact,) = analyze(invoke(0x6E, ADD_IDX, 0, 1, 3), registers=4, ins=3, info=info)  # v1 = this, v2/v3 params
        self.assertEqual(fact.object_values, {("param", 0, "Lcom/x/Main;")})
        self.assertEqual(fact.name_values, {("param", 2, "Ljava/lang/String;")})

    def test_move_object_from16_copies(self) -> None:
        code = const_string(0, 2) + move_object_from16(21, 0) + new_instance(1, 0) + move_object_from16(20, 1)
        code += invoke_range(0x74, ADD_IDX, 19, 3)
        (fact,) = analyze(code, registers=24)
        self.assertEqual(fact.name_values, {("str", "C", None)})
        self.assertEqual(fact.object_values, {("new", BRIDGE)})

    def test_too_many_names_is_top(self) -> None:
        code = b""  # nine blocks, each setting v0 to a new string and jumping to the call
        tail = 9 * 5
        for i in range(9):
            here = i * 5
            code += const_string(0, i) + if_eqz(3, tail - (here + 2))  # if v3 == 0 jump to the call
            code += b"\x00\x00"  # nop
        code += new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0)
        (fact,) = analyze(code)
        self.assertEqual(fact.name_values, {TOP})

    def test_exception_handler_entry_is_top(self) -> None:
        code = const_string(0, 0) + return_void() + new_instance(1, 0) + invoke(0x6E, ADD_IDX, 2, 1, 0)
        (fact,) = analyze(code, handlers={0: [3]})
        self.assertEqual(fact.name_values, {TOP})

    def test_remove(self) -> None:
        (fact,) = analyze(const_string(0, 0) + invoke(0x6E, REMOVE_IDX, 2, 0))
        self.assertEqual((fact.kind, fact.name_values), (REMOVE, {("str", "A", None)}))


def u_nop() -> bytes:
    return b"\x00\x00"


if __name__ == "__main__":
    unittest.main()
