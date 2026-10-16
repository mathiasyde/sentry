"""core/static: DEX file reader: id tables, class defs and data, annotations, static values, code items."""

from __future__ import annotations

import re
import struct
from functools import lru_cache
from typing import Iterator, NamedTuple

NO_INDEX = 0xFFFFFFFF
MAGIC_RE = re.compile(rb"^dex\n0[3-4][0-9]\x00$")
ACC_PUBLIC = 0x1
ACC_STATIC = 0x8
ACC_INTERFACE = 0x200

VALUE_STRING = 0x17
VALUE_ARRAY = 0x1C
VALUE_ANNOTATION = 0x1D
VALUE_NULL = 0x1E
VALUE_BOOLEAN = 0x1F

PRIMITIVES = {
    "V": "void", "Z": "boolean", "B": "byte", "S": "short", "C": "char",
    "I": "int", "J": "long", "F": "float", "D": "double",
}


class ClassDef(NamedTuple):
    descriptor: str
    access_flags: int
    superclass: str | None
    interfaces: tuple[str, ...]
    annotations_off: int
    class_data_off: int
    static_values_off: int


class EncodedMethod(NamedTuple):
    method_idx: int
    access_flags: int
    code_off: int


class CodeItem(NamedTuple):
    registers_size: int
    ins_size: int
    insns: bytes
    tries: list[tuple[int, int, int]]
    handlers: dict[int, list[int]]


def descriptor_to_java(desc: str) -> str:
    dims = len(desc) - len(desc.lstrip("["))
    base = desc[dims:]
    if base.startswith("L") and base.endswith(";"):
        name = base[1:-1].replace("/", ".")
    else:
        name = PRIMITIVES.get(base, base)
    return name + "[]" * dims


def decode_mutf8(raw: bytes) -> str:
    text = raw.replace(b"\xc0\x80", b"\x00").decode("utf-8", errors="surrogatepass")
    return text.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")


class DexFile:
    def __init__(self, data: bytes, name: str = "classes.dex") -> None:
        if len(data) < 0x70 or not MAGIC_RE.match(data[:8]):
            raise ValueError(f"{name}: not a dex file")
        self.data = data
        self.name = name
        (
            self.string_ids_size, self.string_ids_off,
            self.type_ids_size, self.type_ids_off,
            self.proto_ids_size, self.proto_ids_off,
            self.field_ids_size, self.field_ids_off,
            self.method_ids_size, self.method_ids_off,
            self.class_defs_size, self.class_defs_off,
        ) = struct.unpack_from("<12I", data, 0x38)
        self.string = lru_cache(maxsize=None)(self._string)
        self.type_name = lru_cache(maxsize=None)(self._type_name)
        self.proto = lru_cache(maxsize=None)(self._proto)

    # --- primitives -------------------------------------------------------------------------
    def u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.data, off)[0]

    def uleb(self, off: int) -> tuple[int, int]:
        result = shift = 0
        data = self.data
        while True:
            byte = data[off]
            off += 1
            result |= (byte & 0x7F) << shift
            if byte < 0x80:
                return result, off
            shift += 7

    def sleb(self, off: int) -> tuple[int, int]:
        result = shift = 0
        while True:
            byte = self.data[off]
            off += 1
            result |= (byte & 0x7F) << shift
            shift += 7
            if byte < 0x80:
                return (result - (1 << shift) if byte & 0x40 else result), off

    # --- id tables --------------------------------------------------------------------------
    def string_raw(self, idx: int) -> bytes:
        off = self.u32(self.string_ids_off + 4 * idx)
        _, off = self.uleb(off)
        return self.data[off : self.data.index(b"\x00", off)]

    def _string(self, idx: int) -> str:
        return decode_mutf8(self.string_raw(idx))

    def find_string(self, text: str) -> int | None:
        """Binary search: string_ids are sorted by UTF-16 code unit order."""
        key = text.encode("utf-16-be")
        lo, hi = 0, self.string_ids_size - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            probe = self.string(mid).encode("utf-16-be", errors="surrogatepass")
            if probe == key:
                return mid
            if probe < key:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def find_type(self, descriptor: str) -> int | None:
        string_idx = self.find_string(descriptor)
        if string_idx is None:
            return None
        lo, hi = 0, self.type_ids_size - 1
        while lo <= hi:  # type_ids are sorted by string index
            mid = (lo + hi) // 2
            value = self.u32(self.type_ids_off + 4 * mid)
            if value == string_idx:
                return mid
            lo, hi = (mid + 1, hi) if value < string_idx else (lo, mid - 1)
        return None

    def _type_name(self, idx: int) -> str:
        return self.string(self.u32(self.type_ids_off + 4 * idx))

    def type_list(self, off: int) -> tuple[str, ...]:
        if off == 0:
            return ()
        size = self.u32(off)
        return tuple(self.type_name(i) for i in struct.unpack_from(f"<{size}H", self.data, off + 4))

    def _proto(self, idx: int) -> tuple[str, tuple[str, ...]]:
        _shorty, return_idx, params_off = struct.unpack_from("<III", self.data, self.proto_ids_off + 12 * idx)
        return self.type_name(return_idx), self.type_list(params_off)

    def field(self, idx: int) -> tuple[str, str, str]:
        class_idx, type_idx, name_idx = struct.unpack_from("<HHI", self.data, self.field_ids_off + 8 * idx)
        return self.type_name(class_idx), self.type_name(type_idx), self.string(name_idx)

    def method_raw(self, idx: int) -> tuple[int, int, int]:
        return struct.unpack_from("<HHI", self.data, self.method_ids_off + 8 * idx)

    def method(self, idx: int) -> tuple[str, str, tuple[str, tuple[str, ...]]]:
        class_idx, proto_idx, name_idx = self.method_raw(idx)
        return self.type_name(class_idx), self.string(name_idx), self.proto(proto_idx)

    # --- classes ----------------------------------------------------------------------------
    def class_defs(self) -> Iterator[ClassDef]:
        for i in range(self.class_defs_size):
            (class_idx, access, super_idx, interfaces_off, _src, annotations_off, data_off, static_off) = struct.unpack_from(
                "<8I", self.data, self.class_defs_off + 32 * i
            )
            yield ClassDef(
                self.type_name(class_idx), access,
                None if super_idx == NO_INDEX else self.type_name(super_idx),
                self.type_list(interfaces_off), annotations_off, data_off, static_off,
            )

    def class_data(self, cdef: ClassDef) -> tuple[list[int], list[EncodedMethod]]:
        """(static field indexes, direct + virtual methods)."""
        if cdef.class_data_off == 0:
            return [], []
        off = cdef.class_data_off
        sizes = []
        for _ in range(4):
            value, off = self.uleb(off)
            sizes.append(value)
        static_fields: list[int] = []
        for count, keep in ((sizes[0], True), (sizes[1], False)):
            idx = 0
            for _ in range(count):
                diff, off = self.uleb(off)
                _flags, off = self.uleb(off)
                idx += diff
                if keep:
                    static_fields.append(idx)
        methods: list[EncodedMethod] = []
        for count in (sizes[2], sizes[3]):
            idx = 0
            for _ in range(count):
                diff, off = self.uleb(off)
                flags, off = self.uleb(off)
                code_off, off = self.uleb(off)
                idx += diff
                methods.append(EncodedMethod(idx, flags, code_off))
        return static_fields, methods

    def static_string_values(self, cdef: ClassDef) -> dict[int, str]:
        if cdef.static_values_off == 0:
            return {}
        fields, _ = self.class_data(cdef)
        size, off = self.uleb(cdef.static_values_off)
        values: dict[int, str] = {}
        for i in range(size):
            header = self.data[off]
            if (header & 0x1F) == VALUE_STRING and i < len(fields):
                width = (header >> 5) + 1
                values[fields[i]] = self.string(int.from_bytes(self.data[off + 1 : off + 1 + width], "little"))
            off = self.skip_value(off)
        return values

    def skip_value(self, off: int) -> int:
        header = self.data[off]
        value_type, arg = header & 0x1F, header >> 5
        off += 1
        if value_type == VALUE_ARRAY:
            size, off = self.uleb(off)
            for _ in range(size):
                off = self.skip_value(off)
            return off
        if value_type == VALUE_ANNOTATION:
            return self.skip_annotation(off)
        if value_type in (VALUE_NULL, VALUE_BOOLEAN):
            return off
        return off + arg + 1

    def skip_annotation(self, off: int) -> int:
        _type_idx, off = self.uleb(off)
        size, off = self.uleb(off)
        for _ in range(size):
            _name, off = self.uleb(off)
            off = self.skip_value(off)
        return off

    def method_annotation_types(self, cdef: ClassDef) -> dict[int, set[str]]:
        if cdef.annotations_off == 0:
            return {}
        _class_ann, fields_size, methods_size, _params = struct.unpack_from("<4I", self.data, cdef.annotations_off)
        off = cdef.annotations_off + 16 + 8 * fields_size
        result: dict[int, set[str]] = {}
        for i in range(methods_size):
            method_idx, set_off = struct.unpack_from("<II", self.data, off + 8 * i)
            types = set()
            for j in range(self.u32(set_off)):
                item = self.u32(set_off + 4 + 4 * j)
                type_idx, _ = self.uleb(item + 1)  # skip the visibility byte
                types.add(self.type_name(type_idx))
            result[method_idx] = types
        return result

    # --- code -------------------------------------------------------------------------------
    def raw_insns(self, code_off: int) -> bytes:
        insns_size = self.u32(code_off + 12)
        return self.data[code_off + 16 : code_off + 16 + 2 * insns_size]

    def code(self, code_off: int) -> CodeItem:
        registers, ins, _outs, tries_size = struct.unpack_from("<4H", self.data, code_off)
        insns_size = self.u32(code_off + 12)
        insns = self.data[code_off + 16 : code_off + 16 + 2 * insns_size]
        tries: list[tuple[int, int, int]] = []
        handlers: dict[int, list[int]] = {}
        if tries_size:
            off = code_off + 16 + 2 * insns_size + (2 if insns_size % 2 else 0)
            for i in range(tries_size):
                tries.append(struct.unpack_from("<IHH", self.data, off + 8 * i))
            list_off = off + 8 * tries_size
            for _start, _count, handler_off in tries:
                if handler_off not in handlers:
                    handlers[handler_off] = self.handler_addresses(list_off + handler_off)
        return CodeItem(registers, ins, insns, tries, handlers)

    def handler_addresses(self, off: int) -> list[int]:
        size, off = self.sleb(off)
        addresses = []
        for _ in range(abs(size)):
            _type_idx, off = self.uleb(off)
            addr, off = self.uleb(off)
            addresses.append(addr)
        if size <= 0:
            addr, off = self.uleb(off)
            addresses.append(addr)
        return addresses
