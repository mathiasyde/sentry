"""core/static: Dalvik instruction widths and decoding of the opcodes the bridge analysis needs."""

from __future__ import annotations

import struct
from typing import Iterator, NamedTuple


def _formats() -> list[str]:
    table = ["10x"] * 256
    spans = [
        (0x00, 0x00, "10x"), (0x01, 0x01, "12x"), (0x02, 0x02, "22x"), (0x03, 0x03, "32x"),
        (0x04, 0x04, "12x"), (0x05, 0x05, "22x"), (0x06, 0x06, "32x"),
        (0x07, 0x07, "12x"), (0x08, 0x08, "22x"), (0x09, 0x09, "32x"),
        (0x0A, 0x0D, "11x"), (0x0E, 0x0E, "10x"), (0x0F, 0x11, "11x"),
        (0x12, 0x12, "11n"), (0x13, 0x13, "21s"), (0x14, 0x14, "31i"), (0x15, 0x15, "21h"),
        (0x16, 0x16, "21s"), (0x17, 0x17, "31i"), (0x18, 0x18, "51l"), (0x19, 0x19, "21h"),
        (0x1A, 0x1A, "21c"), (0x1B, 0x1B, "31c"), (0x1C, 0x1C, "21c"), (0x1D, 0x1E, "11x"),
        (0x1F, 0x1F, "21c"), (0x20, 0x20, "22c"), (0x21, 0x21, "12x"), (0x22, 0x22, "21c"),
        (0x23, 0x23, "22c"), (0x24, 0x24, "35c"), (0x25, 0x25, "3rc"), (0x26, 0x26, "31t"),
        (0x27, 0x27, "11x"), (0x28, 0x28, "10t"), (0x29, 0x29, "20t"), (0x2A, 0x2A, "30t"),
        (0x2B, 0x2C, "31t"), (0x2D, 0x31, "23x"), (0x32, 0x37, "22t"), (0x38, 0x3D, "21t"),
        (0x44, 0x51, "23x"), (0x52, 0x5F, "22c"), (0x60, 0x6D, "21c"),
        (0x6E, 0x72, "35c"), (0x74, 0x78, "3rc"), (0x7B, 0x8F, "12x"), (0x90, 0xAF, "23x"),
        (0xB0, 0xCF, "12x"), (0xD0, 0xD7, "22s"), (0xD8, 0xE2, "22b"),
        (0xFA, 0xFA, "45cc"), (0xFB, 0xFB, "4rcc"), (0xFC, 0xFC, "35c"), (0xFD, 0xFD, "3rc"),
        (0xFE, 0xFF, "21c"),
    ]
    for first, last, fmt in spans:
        for op in range(first, last + 1):
            table[op] = fmt
    return table


FORMATS = _formats()
WIDTHS = [int(fmt[0]) for fmt in FORMATS]

CONST_STRING, CONST_STRING_JUMBO = 0x1A, 0x1B
MOVE_OBJECT = {0x07, 0x08, 0x09}
MOVE_RESULT_OBJECT = 0x0C
CHECK_CAST, NEW_INSTANCE = 0x1F, 0x22
IGET_OBJECT, SGET_OBJECT = 0x54, 0x62
INVOKE = set(range(0x6E, 0x73)) | set(range(0x74, 0x79)) | {0xFA, 0xFB, 0xFC, 0xFD}
INVOKE_STATIC = {0x71, 0x77}
FILLED_NEW_ARRAY = {0x24, 0x25}
GOTO = {0x28, 0x29, 0x2A}
IF = set(range(0x32, 0x3E))
SWITCH = {0x2B, 0x2C}
TERMINAL = set(range(0x0E, 0x12)) | {0x27} | GOTO
BRANCH = GOTO | IF | SWITCH

# Opcodes whose first register operand is written.
WRITES = (
    set(range(0x01, 0x0E)) | set(range(0x12, 0x1D)) | {0x1F, 0x20, 0x21, 0x22, 0x23}
    | set(range(0x2D, 0x32)) | set(range(0x44, 0x4B)) | set(range(0x52, 0x59)) | set(range(0x60, 0x67))
    | set(range(0x7B, 0xE3)) | {0xFE, 0xFF}
)
WIDE_DEST = (
    {0x04, 0x05, 0x06, 0x0B, 0x16, 0x17, 0x18, 0x19, 0x45, 0x53, 0x61}
    | {0x7D, 0x7E, 0x80, 0x81, 0x83, 0x86, 0x88, 0x89, 0x8B}
    | set(range(0x9B, 0xA6)) | set(range(0xAB, 0xB0)) | set(range(0xBB, 0xC6)) | set(range(0xCB, 0xD0))
)


class Insn(NamedTuple):
    offset: int
    op: int
    regs: tuple[int, ...]  # destination first where applicable; invoke: argument registers
    ref: int | None  # string/type/field/method index
    targets: tuple[int, ...]  # branch targets (absolute code-unit offsets)
    writes: tuple[int, ...]


def unit(insns: bytes, index: int) -> int:
    return struct.unpack_from("<H", insns, 2 * index)[0]


def payload_size(insns: bytes, index: int) -> int:
    ident = unit(insns, index)
    if ident == 0x0100:
        return unit(insns, index + 1) * 2 + 4
    if ident == 0x0200:
        return unit(insns, index + 1) * 4 + 2
    if ident == 0x0300:
        width = unit(insns, index + 1)
        size = struct.unpack_from("<I", insns, 2 * index + 4)[0]
        return (size * width + 1) // 2 + 4
    return 1


def iter_insns(insns: bytes) -> Iterator[tuple[int, int, int]]:
    """(offset, opcode, width in code units); payload pseudo-instructions are skipped."""
    total = len(insns) // 2
    index = 0
    while index < total:
        op = insns[2 * index]
        if op == 0x00 and insns[2 * index + 1] != 0x00:
            index += payload_size(insns, index)
            continue
        width = WIDTHS[op]
        yield index, op, width
        index += width


def switch_targets(insns: bytes, offset: int, payload: int, op: int) -> tuple[int, ...]:
    base = offset + payload
    size = unit(insns, base + 1)
    first = base + 2 if op == 0x2B else base + 2 + 2 * size
    if op == 0x2B:
        first += 2  # skip first_key
    return tuple(offset + struct.unpack_from("<i", insns, 2 * first + 4 * i)[0] for i in range(size))


def signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def decode(insns: bytes, offset: int) -> Insn:
    u0 = unit(insns, offset)
    op, hi = u0 & 0xFF, u0 >> 8
    fmt = FORMATS[op]
    regs: tuple[int, ...] = ()
    ref = None
    targets: tuple[int, ...] = ()
    if fmt == "12x":
        regs = (hi & 0xF, hi >> 4)
    elif fmt in ("11x", "11n"):
        regs = (hi if fmt == "11x" else hi & 0xF,)
    elif fmt == "22x":
        regs = (hi, unit(insns, offset + 1))
    elif fmt == "32x":
        regs = (unit(insns, offset + 1), unit(insns, offset + 2))
    elif fmt in ("21c", "21s", "21h", "21t", "22b", "23x", "31i", "31t", "51l"):
        regs = (hi,)
        if fmt == "21c":
            ref = unit(insns, offset + 1)
        elif fmt == "21t":
            targets = (offset + signed(unit(insns, offset + 1), 16),)
        elif fmt == "31t":
            payload = struct.unpack_from("<i", insns, 2 * offset + 2)[0]
            targets = switch_targets(insns, offset, payload, op) if op in SWITCH else ()
    elif fmt == "31c":
        regs, ref = (hi,), struct.unpack_from("<I", insns, 2 * offset + 2)[0]
    elif fmt in ("22c", "22s", "22t"):
        regs = (hi & 0xF, hi >> 4)
        if fmt == "22c":
            ref = unit(insns, offset + 1)
        elif fmt == "22t":
            targets = (offset + signed(unit(insns, offset + 1), 16),)
    elif fmt in ("35c", "45cc"):
        count, g = hi >> 4, hi & 0xF
        ref = unit(insns, offset + 1)
        cdef = unit(insns, offset + 2)
        regs = (cdef & 0xF, (cdef >> 4) & 0xF, (cdef >> 8) & 0xF, cdef >> 12, g)[:count]
    elif fmt in ("3rc", "4rcc"):
        ref, first = unit(insns, offset + 1), unit(insns, offset + 2)
        regs = tuple(range(first, first + hi))
    elif fmt == "10t":
        targets = (offset + signed(hi, 8),)
    elif fmt == "20t":
        targets = (offset + signed(unit(insns, offset + 1), 16),)
    elif fmt == "30t":
        targets = (offset + struct.unpack_from("<i", insns, 2 * offset + 2)[0],)
    writes: tuple[int, ...] = ()
    if op in WRITES and regs:
        writes = (regs[0], regs[0] + 1) if op in WIDE_DEST else (regs[0],)
    return Insn(offset, op, regs, ref, targets, writes)
