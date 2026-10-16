"""core/static: find exposed methods and bridge registrations across all dex files and link them."""

from __future__ import annotations

import struct
from typing import Any, NamedTuple

from core.report.rules.catalog import SENSITIVE_METHOD_RE
from core.static import insns as I
from core.static.dataflow import ADD, TOP, CallSiteFact, MethodInfo, analyze_method
from core.static.dex import DexFile, descriptor_to_java
from core.static.index import OBJECT, ClassIndex, DexResolver, is_public, is_static

PRE_17 = 17
J = descriptor_to_java


class Site(NamedTuple):
    fact: CallSiteFact
    call_site: dict[str, Any]
    receiver: str


def scan_dex(dex: DexFile, index: ClassIndex, stats: dict) -> list[Site]:
    """Every bridge add/remove call site in one dex file."""
    resolver = DexResolver(dex, index)
    if not resolver.targets:
        return []
    needles = [struct.pack("<H", idx) for idx in resolver.targets]
    sites: list[Site] = []
    for cdef in dex.class_defs():
        for method in dex.class_data(cdef)[1]:
            if not method.code_off or not has_candidate_invoke(dex.raw_insns(method.code_off), needles):
                continue
            stats["methods_scanned"] += 1
            _cls, name, (_ret, params) = dex.method(method.method_idx)
            info = MethodInfo(cdef.descriptor, is_static(method.access_flags), params)
            for fact in analyze_method(dex.code(method.code_off), info, resolver):
                call_site = {
                    "class": J(cdef.descriptor),
                    "method": name,
                    "signature": f"{name}({','.join(J(p) for p in params)})",
                    "dex": dex.name,
                    "offset": fact.offset,
                }
                sites.append(Site(fact, call_site, resolver.receivers[fact.method_idx]))
    return sites


def has_candidate_invoke(raw: bytes, needles: list[bytes]) -> bool:
    """Cheap pre-filter: an invoke opcode followed by one of the target method indexes."""
    for needle in needles:
        start = raw.find(needle)
        while start != -1:
            if start % 2 == 0 and start >= 2 and raw[start - 2] in I.INVOKE:
                return True
            start = raw.find(needle, start + 1)
    return False


def exposed_methods(index: Any, descriptor: str, pre17: bool) -> list[dict[str, Any]]:
    """Like Class.getMethods() filtered by @JavascriptInterface: the most-derived public declaration decides."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    exposed = []
    current: str | None = descriptor
    while current and current in index:
        for decl in index.methods(current):
            key = (decl.name, decl.params)
            if key in seen or not is_public(decl.access_flags):
                continue
            seen.add(key)
            if decl.annotated or pre17:
                exposed.append(method_dict(decl, current, "annotation" if decl.annotated else "public-pre-17"))
        current = index.superclass(current)
    return sorted(exposed, key=lambda m: (m["name"], m["params"]))


def method_dict(decl: Any, declared_in: str, exposure: str) -> dict[str, Any]:
    return {
        "name": decl.name,
        "params": [J(p) for p in decl.params],
        "returns": J(decl.returns),
        "declared_in": J(declared_in),
        "exposure": exposure,
        "sensitive": bool(SENSITIVE_METHOD_RE.search(decl.name)),
    }


def capable_classes(index: Any, pre17: bool) -> dict[str, list[dict[str, Any]]]:
    """Annotated classes and their APK subclasses that still expose at least one method."""
    pending = list(index.annotated_classes())
    capable: dict[str, list[dict[str, Any]]] = {}
    while pending:
        descriptor = pending.pop()
        if descriptor in capable:
            continue
        methods = exposed_methods(index, descriptor, pre17)
        capable[descriptor] = methods
        pending.extend(index.subclasses(descriptor))
    return {descriptor: methods for descriptor, methods in capable.items() if methods}


def name_outcomes(values: frozenset) -> list[tuple[str | None, dict[str, Any]]]:
    if values and all(value[0] == "str" for value in values):
        return [
            (text, {"kind": "static-field" if ref else "const-string", "ref": ref})
            for _tag, text, ref in sorted(values, key=lambda v: (v[1], v[2] or ""))
        ]
    other = sorted((v for v in values if v[0] != "str"), key=repr)
    return [(None, name_source(other[0] if other else TOP))]


def name_source(value: tuple) -> dict[str, Any]:
    tag = value[0]
    if tag == "cast":
        return name_source(value[2])
    if tag == "param":
        return {"kind": "parameter", "ref": f"param#{value[1]}"}
    if tag in ("field", "result"):
        return {"kind": "field" if tag == "field" else "method-result", "ref": value[1]}
    return {"kind": "unknown", "ref": None}


def resolve_class(values: frozenset, index: Any, capable: dict) -> tuple[str | None, str, list[str]]:
    news = sorted({v[1] for v in values if v[0] == "new"})
    declared = {declared_type(v) for v in values if v[0] != "new"}
    if news and not declared and len(news) == 1:
        return news[0], "exact", news
    candidates = set(news) | {c for c in capable if any(index.is_assignable(c, d) for d in declared)}
    if not candidates and len(declared) == 1 and next(iter(declared)) not in (OBJECT,):
        only = next(iter(declared))
        return (only, "declared-type", [only]) if only in index else (None, "unknown", [])
    ordered = sorted(candidates)
    if len(ordered) == 1:
        return ordered[0], "declared-type", ordered
    return None, ("ambiguous" if ordered else "unknown"), ordered


def declared_type(value: tuple) -> str:
    tag = value[0]
    if tag == "param":
        return value[2]
    if tag in ("field", "result", "cast"):
        return value[2] if tag != "cast" else value[1]
    return OBJECT


def link(sites: list[Site], index: Any, target_sdk: int | None) -> dict[str, list]:
    pre17 = target_sdk is not None and target_sdk < PRE_17
    capable = capable_classes(index, pre17)
    registrations, removals = [], []
    for site in sites:
        names = name_outcomes(site.fact.name_values)
        if site.fact.kind != ADD:
            for name, source in names:
                removals.append(name_entry(name, source) | {"call_site": site.call_site})
            continue
        cls, resolution, candidates = resolve_class(site.fact.object_values, index, capable)
        if cls and pre17 and cls not in capable:
            capable[cls] = exposed_methods(index, cls, pre17)
        methods = capable.get(cls, []) if cls and resolution in ("exact", "declared-type") else []
        for name, source in names:
            registrations.append(
                name_entry(name, source)
                | {
                    "class_name": J(cls) if cls else None,
                    "class_resolution": resolution,
                    "candidate_classes": [J(c) for c in candidates],
                    "methods": methods,
                    "call_site": site.call_site,
                    "webview_receiver": site.receiver,
                }
            )
    registered = {r["class_name"] for r in registrations} | {c for r in registrations for c in r["candidate_classes"]}
    bridge_classes = [
        {
            "class_name": J(cls),
            "superclass": J(index.superclass(cls)) if index.superclass(cls) else None,
            "methods": methods,
            "registered": J(cls) in registered,
        }
        for cls, methods in capable.items()
        if methods
    ]
    site_key = lambda e: (e["call_site"]["class"], e["call_site"]["signature"], e["call_site"]["offset"])  # noqa: E731
    return {
        "registrations": sorted(registrations, key=lambda r: (r["name"] or "", r["class_name"] or "", *site_key(r))),
        "removals": sorted(removals, key=lambda r: (r["name"] or "", *site_key(r))),
        "bridge_classes": sorted(bridge_classes, key=lambda c: c["class_name"]),
    }


def name_entry(name: str | None, source: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "name_status": "resolved" if name is not None else "unresolved", "name_source": source}


def discover(dexes: list[DexFile], target_sdk: int | None) -> tuple[dict[str, list], dict[str, int]]:
    index = ClassIndex(dexes)
    stats = {"classes": len(index.classes), "methods_scanned": 0}
    sites: list[Site] = []
    for dex in dexes:
        sites.extend(scan_dex(dex, index, stats))
    return link(sites, index, target_sdk), stats
