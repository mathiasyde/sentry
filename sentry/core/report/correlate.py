"""core/report: join static bridge registrations with runtime-observed bridges (pure, no findings)."""

from __future__ import annotations

from typing import Any

from core.report.rules.catalog import SENSITIVE_METHOD_RE

PROVENANCE_ORDER = {"static+runtime": 0, "static-only": 1, "runtime-only": 2}


def runtime_bridges(tracker: Any) -> dict[tuple[str | None, str | None], dict[str, Any]]:
    """(interfaceName, className) -> WebView ids and method names seen at runtime.

    A bridge counts as seen when its registration was hooked, or when one of its methods was called. Calls to
    statically pre-instrumented methods arrive even if the registration was missed (webViewId "unknown",
    interfaceName possibly null).
    """
    bridges: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for webview_id, state in tracker.webviews.items():
        methods_by_name: dict[str, set[str]] = {}
        for method in state["bridge_methods"]:
            methods_by_name.setdefault(method.get("interfaceName"), set()).add(str(method.get("method") or ""))
        for name, bridge in state["bridges"].items():
            entry = bridges.setdefault((name, bridge.get("className")), {"webviews": set(), "methods": set()})
            entry["webviews"].add(webview_id)
            entry["methods"] |= methods_by_name.get(name, set())
        for call in state["bridge_calls"]:
            key = (call.get("interfaceName"), call.get("className"))
            if key not in bridges and any(cls == key[1] and key[0] in (None, name) for name, cls in bridges):
                continue  # a call on a bridge whose registration was seen: already covered above
            entry = bridges.setdefault(key, {"webviews": set(), "methods": set()})
            entry["webviews"].add(webview_id)
            entry["methods"].add(str(call.get("methodName") or ""))
    return bridges


def matches(registration: dict[str, Any], name: str | None, class_name: str | None) -> bool:
    if registration["name"] is not None and name is not None and registration["name"] != name:
        return False
    if registration["class_name"] is not None:
        return registration["class_name"] == class_name
    return class_name in registration["candidate_classes"]


def static_view(registration: dict[str, Any]) -> dict[str, Any]:
    call_site = {k: v for k, v in registration["call_site"].items() if k not in ("dex", "offset")}
    return {**registration, "call_site": call_site}


def sensitive(static_methods: list[dict[str, Any]], runtime_methods: set[str]) -> list[str]:
    names = {m["name"] for m in static_methods if m.get("sensitive")}
    names |= {m for m in runtime_methods if SENSITIVE_METHOD_RE.search(m)}
    return sorted(names)


def correlate(static: dict[str, Any], tracker: Any) -> dict[str, Any]:
    completed = static.get("status") == "completed"
    registrations = static.get("registrations") or [] if completed else []
    runtime = runtime_bridges(tracker)
    used: set[tuple[str, str | None]] = set()
    grouped: dict[tuple[str | None, str | None], dict[str, Any]] = {}

    for registration in registrations:
        hits = [key for key in runtime if matches(registration, *key)]
        used.update(hits)
        key = (registration["name"], registration["class_name"])
        entry = grouped.get(key)
        if entry is None:
            names = {name for name, _ in hits}
            classes = {cls for _, cls in hits}
            entry = grouped[key] = {
                "interfaceName": registration["name"] or (names.pop() if len(names) == 1 else None),
                "className": registration["class_name"] or (classes.pop() if len(classes) == 1 else None),
                "static": static_view(registration),
                "registered_in": [],
                "runtime_webviews": set(),
                "runtime_methods": set(),
            }
        call_site = registration["call_site"]
        entry["registered_in"].append(f"{call_site['class']}.{call_site['signature']}")
        for hit in hits:
            entry["runtime_webviews"] |= runtime[hit]["webviews"]
            entry["runtime_methods"] |= runtime[hit]["methods"]

    bridges = []
    for entry in grouped.values():
        bridges.append(
            {
                "interfaceName": entry["interfaceName"],
                "className": entry["className"],
                "provenance": "static+runtime" if entry["runtime_webviews"] else "static-only",
                "static": entry["static"],
                "registered_in": sorted(set(entry["registered_in"])),
                "runtime_webviews": sorted(entry["runtime_webviews"]),
                "runtime_methods": sorted(entry["runtime_methods"]),
                "sensitive_methods": sensitive(entry["static"]["methods"], entry["runtime_methods"]),
            }
        )
    for (name, class_name), seen in runtime.items():
        if (name, class_name) in used:
            continue
        bridges.append(
            {
                "interfaceName": name,
                "className": class_name,
                "provenance": "runtime-only",
                "static": None,
                "registered_in": [],
                "runtime_webviews": sorted(seen["webviews"]),
                "runtime_methods": sorted(seen["methods"]),
                "sensitive_methods": sensitive([], seen["methods"]),
            }
        )
    bridges.sort(key=lambda b: (PROVENANCE_ORDER[b["provenance"]], b["interfaceName"] or "", b["className"] or ""))

    bridge_classes = static.get("bridge_classes") or [] if completed else []
    count = lambda kind: sum(1 for b in bridges if b["provenance"] == kind)  # noqa: E731
    return {
        "status": static.get("status"),
        "error": static.get("error"),
        "target_sdk": static.get("target_sdk"),
        "all_public_methods_exposed": bool(static.get("all_public_methods_exposed")),
        "counts": {
            "registrations": len(registrations),
            "unresolved_names": sum(1 for r in registrations if r["name_status"] == "unresolved"),
            "bridge_classes": len(bridge_classes),
            "static_and_runtime": count("static+runtime"),
            "static_only": count("static-only"),
            "runtime_only": count("runtime-only"),
        },
        "bridges": bridges,
        "unregistered_classes": [c for c in bridge_classes if not c.get("registered")],
        "removals": static.get("removals") or [] if completed else [],
    }
