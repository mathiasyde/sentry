"""core/static: per-activity Intent/URI data shape, for activities that touch a WebView.

Static bridge discovery (core/static/discover.py) answers "what can JavaScript call into the
app?". This module answers the matching question on the way in: "what can the *app* be asked to
load into its WebView, from outside?" For every Activity (or activity-alias) whose code invokes a
method on a WebView-assignable receiver, it combines two sources of the data shape:

  - the manifest's own declared shape: every <intent-filter>'s actions, categories and <data>
    (scheme/host/port/path variants, mimeType), and whether the activity is exported.
  - the shape implied by the code: literal keys read back out of the incoming Intent via
    Intent.getXxxExtra(name), Bundle.getXxx(name) and Uri.getQueryParameter(name)/
    getBooleanQueryParameter(name) inside that activity's class.

Each key is resolved the same way a bridge name is in discover.py: a may-analysis over register
values, constant-propagated through casts, static fields and str literals. A key built at runtime
(concatenated, read from config, returned by another method) is reported as unresolved, along with
where it came from. It is never guessed. Like bridge-name resolution, this works within one method
at a time: a key threaded through a helper method is unresolved.

build_intent_profiles() returns the payload of target/intent-data-profile.json (schema 1).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.static import insns as I
from core.static.apk import Apk
from core.static.axml import activities as manifest_activities
from core.static.axml import manifest_info
from core.static.dataflow import MethodInfo, analyze_method
from core.static.dex import DexFile, descriptor_to_java
from core.static.discover import name_entry, name_outcomes
from core.static.index import WEBVIEW, ClassIndex, is_static

SCHEMA = 1
J = descriptor_to_java

INTENT = "Landroid/content/Intent;"
URI = "Landroid/net/Uri;"
BUNDLE = "Landroid/os/Bundle;"
STRING = "Ljava/lang/String;"

EXTRA = "extra"
QUERY = "query"
BUNDLE_GET = "bundle"

# method name -> kind, keyed by the exact receiver type the call is statically made against.
# All of these take the literal key as their first String parameter.
TARGET_METHODS: dict[str, dict[str, str]] = {
    INTENT: {
        name: EXTRA
        for name in (
            "getStringExtra", "getBooleanExtra", "getIntExtra", "getLongExtra", "getFloatExtra",
            "getDoubleExtra", "getCharSequenceExtra", "getParcelableExtra", "getStringArrayExtra",
            "getStringArrayListExtra", "getBundleExtra", "getSerializableExtra",
        )
    },
    URI: {name: QUERY for name in ("getQueryParameter", "getBooleanQueryParameter")},
    BUNDLE: {
        name: BUNDLE_GET
        for name in (
            "getString", "getBoolean", "getInt", "getLong", "getFloat", "getDouble",
            "getCharSequence", "getParcelable", "getSerializable",
        )
    },
}


class IntentResolver:
    """Resolver protocol (core.static.dataflow) over Intent/Uri/Bundle key-accessor call sites."""

    def __init__(self, dex: DexFile, index: ClassIndex) -> None:
        self.dex = dex
        self.index = index
        self.string = dex.string
        self.type_name = dex.type_name
        self.field = dex.field
        self.method = dex.method
        self.targets: dict[int, str] = {}
        for method_idx in range(dex.method_ids_size):
            cls, name, (_ret, params) = dex.method(method_idx)
            by_name = TARGET_METHODS.get(cls)
            if by_name and name in by_name and params and params[0] == STRING:
                self.targets[method_idx] = by_name[name]

    def static_string(self, field_idx: int) -> str | None:
        return self.index.static_string(self.dex, field_idx)

    def call_kind(self, method_idx: int) -> str | None:
        return self.targets.get(method_idx)


def touches_webview(dex: DexFile, cdef: Any, index: ClassIndex) -> bool:
    """True if some method of this class invokes a method on a WebView-assignable receiver."""
    for method in dex.class_data(cdef)[1]:
        if not method.code_off:
            continue
        insns = dex.raw_insns(method.code_off)
        for offset, op, _width in I.iter_insns(insns):
            if op not in I.INVOKE or op in I.INVOKE_STATIC:
                continue
            receiver, _name, _proto = dex.method(I.decode(insns, offset).ref)
            if index.is_assignable(receiver, WEBVIEW):
                return True
    return False


def resolve_class(manifest_name: str | None, package: str | None) -> str | None:
    """AndroidManifest component names may be package-relative (".Foo") or bare ("Foo")."""
    if not manifest_name:
        return None
    if manifest_name.startswith("."):
        return f"{package}{manifest_name}" if package else manifest_name
    if "." not in manifest_name and package:
        return f"{package}.{manifest_name}"
    return manifest_name


def scan_class(dex: DexFile, cdef: Any, index: ClassIndex) -> list[dict[str, Any]]:
    """Every resolved/unresolved Intent/Uri/Bundle key read inside one class."""
    resolver = IntentResolver(dex, index)
    if not resolver.targets:
        return []
    keys: list[dict[str, Any]] = []
    for method in dex.class_data(cdef)[1]:
        if not method.code_off:
            continue
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
            _accessor_cls, accessor_method, _accessor_proto = resolver.method(fact.method_idx)
            for key, source in name_outcomes(fact.name_values):
                keys.append(
                    name_entry(key, source)
                    | {"accessor": fact.kind, "accessor_method": accessor_method, "call_site": call_site}
                )
    return sorted(keys, key=lambda k: (k["accessor"], k["name"] or "", k["call_site"]["offset"]))


def profile_activities(dexes: list[DexFile], manifest_data: bytes | None) -> list[dict[str, Any]]:
    """Pure core: no APK/filesystem I/O, for testing against fixture dex files and a raw manifest."""
    manifest = manifest_info(manifest_data)
    package = manifest["package"]
    declared = {
        resolve_class(activity["class"], package): activity for activity in manifest_activities(manifest_data)
    }
    index = ClassIndex(dexes)
    profiles = []
    for descriptor, info in index.classes.items():
        activity = declared.get(J(descriptor))
        if activity is None or not touches_webview(info.dex, info.cdef, index):
            continue
        intent_filters = activity["intent_filters"]
        profiles.append(
            {
                "class_name": J(descriptor),
                "exported": activity["exported"] if activity["exported"] is not None else bool(intent_filters),
                "exported_declared": activity["exported"] is not None,
                "intent_filters": intent_filters,
                "intent_keys": scan_class(info.dex, info.cdef, index),
            }
        )
    return sorted(profiles, key=lambda p: p["class_name"])


def build_intent_profiles(apk_path: str | Path) -> dict[str, Any]:
    started = time.monotonic()
    apk = Apk(apk_path)
    try:
        manifest_data = apk.manifest()
        names = apk.dex_names()
        dexes = [DexFile(apk.read(name), name) for name in names]
        profiles = profile_activities(dexes, manifest_data)
        sha256 = apk.sha256()
    finally:
        apk.close()
    manifest = manifest_info(manifest_data)
    return {
        "schema": SCHEMA,
        "status": "completed",
        "error": None,
        "apk": {"path": str(apk_path), "sha256": sha256, "dex_files": names},
        "package": manifest["package"],
        "activities": profiles,
        "stats": {"webview_activities": len(profiles), "seconds": round(time.monotonic() - started, 2)},
    }


def failed_result(apk_path: str | Path, exc: BaseException, seconds: float = 0.0) -> dict[str, Any]:
    error = " ".join(f"{type(exc).__name__}: {exc}".split())[:200]
    return {
        "schema": SCHEMA,
        "status": "failed",
        "error": error,
        "apk": {"path": str(apk_path), "sha256": None, "dex_files": []},
        "package": None,
        "activities": [],
        "stats": {"webview_activities": 0, "seconds": round(seconds, 2)},
    }


def summary_line(result: dict[str, Any], path: str) -> str:
    activities = result["activities"]
    keys = sum(len(a["intent_keys"]) for a in activities)
    unresolved = sum(1 for a in activities for k in a["intent_keys"] if k["name_status"] == "unresolved")
    return (
        f"Intent data profile: {len(activities)} WebView-touching activit{'y' if len(activities) == 1 else 'ies'}, "
        f"{keys} intent key(s), {unresolved} with unresolved names -> {path}"
    )
