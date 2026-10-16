"""core/static: per-method may-analysis of register values to resolve addJavascriptInterface arguments.

Abstract values are tuples:
  ("str", text, field_ref|None)  ("new", T)  ("param", i, T)  ("field", ref, T)
  ("result", ref, T)  ("cast", T, inner)  TOP
A register missing from a state is TOP. The pseudo-register RESULT carries the last invoke's method ref,
so move-result-object knows where its value came from.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol

from core.static import insns as I
from core.static.dex import descriptor_to_java

TOP = ("top",)
RESULT = -1
MAX_VALUES = 8
ADD, REMOVE = "add", "remove"


class Resolver(Protocol):
    def string(self, idx: int) -> str: ...
    def type_name(self, idx: int) -> str: ...
    def field(self, idx: int) -> tuple[str, str, str]: ...  # (class, type, name) descriptors
    def static_string(self, field_idx: int) -> str | None: ...
    def method(self, idx: int) -> tuple[str, str, tuple[str, tuple[str, ...]]]: ...
    def call_kind(self, method_idx: int) -> str | None: ...  # ADD, REMOVE or None


class MethodInfo(NamedTuple):
    declaring_class: str
    is_static: bool
    params: tuple[str, ...]


class CallSiteFact(NamedTuple):
    offset: int
    kind: str
    method_idx: int
    name_values: frozenset
    object_values: frozenset


def entry_state(registers: int, ins: int, info: MethodInfo) -> dict:
    state: dict = {}
    reg = registers - ins
    index = 0
    if not info.is_static:
        state[reg] = frozenset({("param", 0, info.declaring_class)})
        reg, index = reg + 1, 1
    for desc in info.params:
        state[reg] = frozenset({("param", index, desc)})
        reg += 2 if desc in ("J", "D") else 1
        index += 1
    return state


def join(a: dict | None, b: dict) -> dict:
    if a is None:
        return dict(b)
    merged = {}
    for reg, values in a.items():
        other = b.get(reg)
        if other is None:
            continue
        union = values | other
        if TOP not in union and len(union) <= MAX_VALUES:
            merged[reg] = union
    return merged


def put(state: dict, reg: int, values: frozenset | None) -> None:
    if values is None or TOP in values or len(values) > MAX_VALUES:
        state.pop(reg, None)
    else:
        state[reg] = values


def field_ref(resolver: Resolver, idx: int) -> tuple[str, str]:
    """(readable reference such as com.x.Cfg.NAME, declared type descriptor)."""
    cls, desc, name = resolver.field(idx)
    return f"{descriptor_to_java(cls)}.{name}", desc


def method_ref(resolver: Resolver, idx: int) -> tuple[str, str]:
    """(readable reference such as com.x.Cfg.bridgeName(), return type descriptor)."""
    cls, name, (ret, _params) = resolver.method(idx)
    return f"{descriptor_to_java(cls)}.{name}()", ret


def transfer(insn: I.Insn, state: dict, resolver: Resolver) -> dict:
    out = dict(state)
    op, regs = insn.op, insn.regs
    if op in I.INVOKE or op in I.FILLED_NEW_ARRAY:
        out[RESULT] = frozenset({insn.ref if op in I.INVOKE else None})
        return out
    if op != I.MOVE_RESULT_OBJECT:
        out.pop(RESULT, None)
    if op in (I.CONST_STRING, I.CONST_STRING_JUMBO):
        put(out, regs[0], frozenset({("str", resolver.string(insn.ref), None)}))
    elif op in I.MOVE_OBJECT:
        put(out, regs[0], state.get(regs[1]))
    elif op == I.MOVE_RESULT_OBJECT:
        refs = state.get(RESULT, frozenset({None}))
        put(out, regs[0], frozenset(("result", *method_ref(resolver, r)) if r is not None else TOP for r in refs))
        out.pop(RESULT, None)
    elif op == I.NEW_INSTANCE:
        put(out, regs[0], frozenset({("new", resolver.type_name(insn.ref))}))
    elif op == I.CHECK_CAST:
        cast = resolver.type_name(insn.ref)
        inner = state.get(regs[0], frozenset({TOP}))
        put(out, regs[0], frozenset(v if v[0] in ("str", "new") else ("cast", cast, v) for v in inner))
    elif op == I.SGET_OBJECT:
        ref, desc = field_ref(resolver, insn.ref)
        constant = resolver.static_string(insn.ref)
        value = ("str", constant, ref) if constant is not None else ("field", ref, desc)
        put(out, regs[0], frozenset({value}))
    elif op == I.IGET_OBJECT:
        put(out, regs[0], frozenset({("field", *field_ref(resolver, insn.ref))}))
    else:
        for reg in insn.writes:
            out.pop(reg, None)
    return out


def successors(insn: I.Insn, width: int) -> list[int]:
    nexts = list(insn.targets)
    if insn.op not in I.TERMINAL:
        nexts.append(insn.offset + width)
    return nexts


def analyze_method(code, info: MethodInfo, resolver: Resolver) -> list[CallSiteFact]:
    """Forward may-analysis to a fixpoint, then read the argument values at each bridge call site."""
    widths = {offset: width for offset, _op, width in I.iter_insns(code.insns)}
    decoded = {offset: I.decode(code.insns, offset) for offset in widths}
    states: dict[int, dict] = {0: entry_state(code.registers_size, code.ins_size, info)}
    for addresses in code.handlers.values():
        for address in addresses:
            states[address] = {}
    worklist = sorted(states)
    while worklist:
        offset = worklist.pop()
        insn = decoded.get(offset)
        if insn is None:
            continue
        after = transfer(insn, states[offset], resolver)
        for nxt in successors(insn, widths[offset]):
            if nxt not in decoded:
                continue
            merged = join(states.get(nxt), after)
            if merged != states.get(nxt):
                states[nxt] = merged
                worklist.append(nxt)

    facts = []
    for offset in sorted(states):
        insn = decoded.get(offset)
        if insn is None or insn.op not in I.INVOKE or insn.op in I.INVOKE_STATIC:
            continue
        kind = resolver.call_kind(insn.ref)
        if kind is None or len(insn.regs) < (3 if kind == ADD else 2):
            continue
        state = states[offset]
        get = lambda reg: state.get(reg, frozenset({TOP}))  # noqa: E731
        if kind == ADD:
            facts.append(CallSiteFact(offset, kind, insn.ref, get(insn.regs[2]), get(insn.regs[1])))
        else:
            facts.append(CallSiteFact(offset, kind, insn.ref, get(insn.regs[1]), frozenset()))
    return facts
