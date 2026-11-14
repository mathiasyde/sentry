"""core/static: turn one intent_data_profile.py activity profile into `am start` argv(s).

Pure string construction, no adb or process launching here (core/run/intent_launch.py fires these).
Since the
component name (-n) is always given explicitly, Android launches the activity regardless of whether
its intent-filters would actually match the synthesized action/data/categories - those are only
there to shape the Intent object the activity's own code reads back, as closely as the manifest and
the resolved getXxxExtra/getQueryParameter keys allow. An unresolved key (see intent_data_profile.py)
contributes no extra: there's nothing but a None to put in it.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from core.static.intent_data_profile import BUNDLE_GET, EXTRA, QUERY

DEFAULT_ACTION = "android.intent.action.VIEW"
DEFAULT_CATEGORY = "android.intent.category.DEFAULT"
BOOLEAN_HINTS = ("boolean",)
NUMBER_HINTS = ("int", "long", "float", "double")
PLACEHOLDER_STRING = "sentry-probe"


def placeholder_for(key: dict[str, Any]) -> str:
    method = (key.get("accessor_method") or "").lower()
    if any(hint in method for hint in BOOLEAN_HINTS):
        return "true"
    if any(hint in method for hint in NUMBER_HINTS):
        return "1"
    return PLACEHOLDER_STRING


def build_uri(data: dict[str, str] | None, query: list[tuple[str, str]]) -> str | None:
    if not data or not data.get("scheme"):
        return None
    path = data.get("path") or data.get("pathPrefix") or data.get("pathPattern") or data.get("pathSuffix") or ""
    if path and not path.startswith("/"):
        path = f"/{path}"
    port = f":{data['port']}" if data.get("port") else ""
    uri = f"{data['scheme']}://{data.get('host', '')}{port}{path}"
    if query:
        uri += "?" + "&".join(f"{quote(k)}={quote(v)}" for k, v in query)
    return uri


def build_am_commands(package: str, activity: dict[str, Any]) -> list[list[str]]:
    """One `am start` argv (without the leading "adb shell") per distinct intent-filter/data pair."""
    component = f"{package}/{activity['class_name']}"
    resolved = [k for k in activity["intent_keys"] if k["name"]]
    extras = [(k["name"], placeholder_for(k)) for k in resolved if k["accessor"] in (EXTRA, BUNDLE_GET)]
    query = [(k["name"], placeholder_for(k)) for k in resolved if k["accessor"] == QUERY]
    filters = activity["intent_filters"] or [{"actions": [], "categories": [], "data": []}]

    commands, seen = [], set()
    for filt in filters:
        action = filt["actions"][0] if filt["actions"] else DEFAULT_ACTION
        categories = [c for c in filt["categories"] if c != DEFAULT_CATEGORY]
        for data in filt["data"] or [None]:
            uri = build_uri(data, query)
            key = (action, uri, tuple(categories))
            if key in seen:
                continue
            seen.add(key)
            argv = ["am", "start", "-W", "-n", component, "-a", action]
            for category in categories:
                argv += ["-c", category]
            if uri:
                argv += ["-d", uri]
            for name, value in extras:
                argv += ["--es", name, value]
            commands.append(argv)
    return commands
