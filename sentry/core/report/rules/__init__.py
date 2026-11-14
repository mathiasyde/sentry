"""core/report/rules: security detection rules that turn observed events into findings.

Each detector has the signature ``detect(event, data, tracked, findings)`` and is registered for one event type.
Detectors for the same event type run in registration order. They never read files or write output.
"""

from __future__ import annotations

from typing import Any, Callable

from core.events import EventType
from core.report.rules import bridges, javascript, navigation, permissions, settings
from core.report.rules import static_bridges  # noqa: F401  runs once per report from Analyzer, not per event

Detector = Callable[[dict[str, Any], dict[str, Any], dict[str, Any], Any], None]

DETECTORS: dict[str, list[Detector]] = {}


def register(event_type: str, detector: Detector) -> None:
    DETECTORS.setdefault(event_type, []).append(detector)


def run(event_type: str, event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: Any) -> None:
    for detector in DETECTORS.get(event_type, []):
        detector(event, data, tracked, findings)


register(EventType.URL_LOADED, navigation.detect_url_loaded)
register(EventType.WEBVIEW_SETTINGS_CHANGED, settings.detect_setting_changed)
register(EventType.BRIDGE_ADDED, bridges.detect_bridge_added)
register(EventType.BRIDGE_METHOD_ADDED, bridges.detect_bridge_method_added)
register(EventType.BRIDGE_METHOD_CALLED, bridges.detect_bridge_method_called)
register(EventType.PERMISSION_REQUESTED, permissions.detect_permission_requested)
register(EventType.PERMISSION_GRANT_CALLED, permissions.detect_permission_granted)
register(EventType.JS_EVALUATED, javascript.detect_js_evaluated)
register(EventType.JS_PROBE, javascript.detect_js_probe)
register(EventType.JS_PROBE_ERROR, javascript.detect_probe_error)
