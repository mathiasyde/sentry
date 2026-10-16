"""core/static: class index across all dex files, and the per-dex resolver the dataflow analysis queries."""

from __future__ import annotations

from typing import NamedTuple

from core.static.dataflow import ADD, REMOVE
from core.static.dex import ACC_PUBLIC, ACC_STATIC, ClassDef, DexFile

JAVASCRIPT_INTERFACE = "Landroid/webkit/JavascriptInterface;"
WEBVIEW = "Landroid/webkit/WebView;"
OBJECT = "Ljava/lang/Object;"
CALLS = {
    "addJavascriptInterface": (ADD, ("Ljava/lang/Object;", "Ljava/lang/String;")),
    "removeJavascriptInterface": (REMOVE, ("Ljava/lang/String;",)),
}


class MethodDecl(NamedTuple):
    name: str
    params: tuple[str, ...]
    returns: str
    access_flags: int
    annotated: bool


class ClassInfo(NamedTuple):
    descriptor: str
    superclass: str | None
    interfaces: tuple[str, ...]
    access_flags: int
    dex: DexFile
    cdef: ClassDef


class ClassIndex:
    """First definition of each class wins, in multidex load order (like the runtime class loader)."""

    def __init__(self, dexes: list[DexFile]) -> None:
        self.dexes = dexes
        self.classes: dict[str, ClassInfo] = {}
        for dex in dexes:
            for cdef in dex.class_defs():
                if cdef.descriptor not in self.classes:
                    self.classes[cdef.descriptor] = ClassInfo(
                        cdef.descriptor, cdef.superclass, cdef.interfaces, cdef.access_flags, dex, cdef
                    )
        self._methods: dict[str, list[MethodDecl]] = {}
        self._statics: dict[int, dict[int, str]] = {}

    def __contains__(self, descriptor: str) -> bool:
        return descriptor in self.classes

    def superclass(self, descriptor: str) -> str | None:
        info = self.classes.get(descriptor)
        return info.superclass if info else None

    def subclasses(self, descriptor: str) -> list[str]:
        if not hasattr(self, "_children"):
            self._children: dict[str, list[str]] = {}
            for info in self.classes.values():
                if info.superclass:
                    self._children.setdefault(info.superclass, []).append(info.descriptor)
        return self._children.get(descriptor, [])

    def methods(self, descriptor: str) -> list[MethodDecl]:
        """Methods declared by a class in the APK (constructors excluded)."""
        if descriptor not in self._methods:
            info = self.classes.get(descriptor)
            decls: list[MethodDecl] = []
            if info is not None:
                dex = info.dex
                annotations = dex.method_annotation_types(info.cdef)
                for method in dex.class_data(info.cdef)[1]:
                    _cls, name, (ret, params) = dex.method(method.method_idx)
                    if name in ("<init>", "<clinit>"):
                        continue
                    annotated = JAVASCRIPT_INTERFACE in annotations.get(method.method_idx, ())
                    decls.append(MethodDecl(name, params, ret, method.access_flags, annotated))
            self._methods[descriptor] = decls
        return self._methods[descriptor]

    def annotated_classes(self) -> list[str]:
        found = []
        for dex in self.dexes:
            if dex.find_type(JAVASCRIPT_INTERFACE) is None:
                continue
            for cdef in dex.class_defs():
                if self.classes[cdef.descriptor].cdef != cdef or not cdef.annotations_off:
                    continue
                if any(JAVASCRIPT_INTERFACE in types for types in dex.method_annotation_types(cdef).values()):
                    found.append(cdef.descriptor)
        return found

    def supertypes(self, descriptor: str) -> set[str]:
        """The class, its superclasses and all interfaces it implements, as far as the APK defines them."""
        seen: set[str] = set()
        pending = [descriptor]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            info = self.classes.get(current)
            if info is not None:
                pending.extend(info.interfaces)
                if info.superclass:
                    pending.append(info.superclass)
        return seen | {OBJECT}

    def is_assignable(self, descriptor: str, target: str) -> bool:
        return target == OBJECT or target in self.supertypes(descriptor)

    def webview_receiver(self, descriptor: str) -> str | None:
        """'verified' for WebView or an APK subclass of it, 'unverified' for unknown classes, None otherwise."""
        current = descriptor
        while current:
            if current == WEBVIEW:
                return "verified"
            info = self.classes.get(current)
            if info is None:
                return None if current == OBJECT else "unverified"
            current = info.superclass
        return None

    def static_string(self, dex: DexFile, field_idx: int) -> str | None:
        cls, _type, name = dex.field(field_idx)
        info = self.classes.get(cls)
        if info is None:
            return None
        key = id(info.cdef)
        if key not in self._statics:
            self._statics[key] = {
                info.dex.field(idx)[2]: value for idx, value in info.dex.static_string_values(info.cdef).items()
            }
        return self._statics[key].get(name)


class DexResolver:
    """Adapts one dex file plus the global class index to the dataflow Resolver protocol."""

    def __init__(self, dex: DexFile, index: ClassIndex) -> None:
        self.dex = dex
        self.index = index
        self.string = dex.string
        self.type_name = dex.type_name
        self.field = dex.field
        self.method = dex.method
        self.targets: dict[int, str] = {}
        self.receivers: dict[int, str] = {}
        for name, (kind, params) in CALLS.items():
            name_idx = dex.find_string(name)
            if name_idx is None:
                continue
            for method_idx in range(dex.method_ids_size):
                _class_idx, _proto_idx, method_name_idx = dex.method_raw(method_idx)
                if method_name_idx != name_idx:
                    continue
                cls, _name, (ret, proto_params) = dex.method(method_idx)
                receiver = index.webview_receiver(cls)
                if ret == "V" and proto_params == params and receiver is not None:
                    self.targets[method_idx] = kind
                    self.receivers[method_idx] = receiver

    def static_string(self, field_idx: int) -> str | None:
        return self.index.static_string(self.dex, field_idx)

    def call_kind(self, method_idx: int) -> str | None:
        return self.targets.get(method_idx)


def is_public(flags: int) -> bool:
    return bool(flags & ACC_PUBLIC)


def is_static(flags: int) -> bool:
    return bool(flags & ACC_STATIC)
