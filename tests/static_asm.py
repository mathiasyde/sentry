"""Tiny Dalvik assembler and fake resolver/index for the core/static unit tests."""

from __future__ import annotations

import struct
from typing import NamedTuple

from core.static.dataflow import ADD, REMOVE
from core.static.index import MethodDecl

ADD_IDX, REMOVE_IDX = 100, 101


def u(*units: int) -> bytes:
    return struct.pack(f"<{len(units)}H", *units)


def const_string(reg: int, idx: int) -> bytes:
    return u(0x1A | reg << 8, idx)


def new_instance(reg: int, type_idx: int) -> bytes:
    return u(0x22 | reg << 8, type_idx)


def invoke(op: int, method_idx: int, *regs: int) -> bytes:
    padded = list(regs) + [0] * (5 - len(regs))
    c, d, e, f, g = padded
    return u(op | (len(regs) << 12) | (g << 8), method_idx, c | d << 4 | e << 8 | f << 12)


def invoke_range(op: int, method_idx: int, first: int, count: int) -> bytes:
    return u(op | count << 8, method_idx, first)


def move_result_object(reg: int) -> bytes:
    return u(0x0C | reg << 8)


def move_object_from16(dst: int, src: int) -> bytes:
    return u(0x08 | dst << 8, src)


def sget_object(reg: int, field_idx: int) -> bytes:
    return u(0x62 | reg << 8, field_idx)


def if_eqz(reg: int, delta: int) -> bytes:
    return u(0x38 | reg << 8, delta & 0xFFFF)


def goto(delta: int) -> bytes:
    return u(0x28 | (delta & 0xFF) << 8)


def return_void() -> bytes:
    return u(0x0E)


class Code(NamedTuple):
    registers_size: int
    ins_size: int
    insns: bytes
    tries: list = []
    handlers: dict = {}


class FakeResolver:
    def __init__(self, strings=None, types=None, fields=None, statics=None, methods=None) -> None:
        self.strings = strings or {}
        self.types = types or {}
        self.fields = fields or {}
        self.statics = statics or {}
        self.methods = {
            ADD_IDX: ("Landroid/webkit/WebView;", "addJavascriptInterface", ("V", ("Ljava/lang/Object;", "Ljava/lang/String;"))),
            REMOVE_IDX: ("Landroid/webkit/WebView;", "removeJavascriptInterface", ("V", ("Ljava/lang/String;",))),
            **(methods or {}),
        }

    def string(self, idx):
        return self.strings[idx]

    def type_name(self, idx):
        return self.types[idx]

    def field(self, idx):
        return self.fields[idx]

    def static_string(self, idx):
        return self.statics.get(idx)

    def method(self, idx):
        return self.methods[idx]

    def call_kind(self, idx):
        return {ADD_IDX: ADD, REMOVE_IDX: REMOVE}.get(idx)


class FakeIndex:
    """classes: descriptor -> (superclass, [MethodDecl]); annotated classes are derived from the decls."""

    def __init__(self, classes: dict[str, tuple[str | None, list[MethodDecl]]], interfaces=None) -> None:
        self.classes = classes
        self.interfaces = interfaces or {}

    def __contains__(self, descriptor):
        return descriptor in self.classes

    def superclass(self, descriptor):
        return self.classes[descriptor][0] if descriptor in self.classes else None

    def methods(self, descriptor):
        return self.classes.get(descriptor, (None, []))[1]

    def subclasses(self, descriptor):
        return [name for name, (sup, _) in self.classes.items() if sup == descriptor]

    def annotated_classes(self):
        return [name for name, (_, decls) in self.classes.items() if any(d.annotated for d in decls)]

    def is_assignable(self, descriptor, target):
        if target == "Ljava/lang/Object;":
            return True
        current = descriptor
        while current:
            if current == target or target in self.interfaces.get(current, ()):
                return True
            current = self.superclass(current)
        return False


def decl(name: str, annotated: bool = True, public: bool = True, params=(), returns="V") -> MethodDecl:
    return MethodDecl(name, tuple(params), returns, 0x1 if public else 0x2, annotated)
