"""core/report: dispatch each event to its state tracker and then to its detectors; assemble the report."""

from __future__ import annotations

from typing import Any

from core.events import EventType
from core.report import assemble, correlate, rules
from core.report.rules import static_bridges
from core.report.findings import FindingStore
from core.report.tracker import WebViewTracker

TRACKERS = {
    EventType.URL_LOADED: "track_url",
    EventType.WEBVIEW_SETTINGS_CHANGED: "track_setting",
    EventType.BRIDGE_ADDED: "track_bridge_added",
    EventType.BRIDGE_METHOD_ADDED: "track_bridge_method",
    EventType.BRIDGE_METHOD_CALLED: "track_bridge_call",
    EventType.PERMISSION_REQUESTED: "track_untracked",
    EventType.PERMISSION_GRANT_CALLED: "track_untracked",
    EventType.JS_EVALUATED: "track_untracked",
    EventType.JS_PROBE: "track_js_probe",
    EventType.JS_PROBE_ERROR: "track_untracked",
}


class Analyzer:
    def __init__(self, trusted_origins: set[str], static: dict[str, Any] | None = None) -> None:
        self.tracker = WebViewTracker(trusted_origins)
        self.findings = FindingStore()
        self.static = static

    def observe(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if not isinstance(event_type, str) or event_type not in TRACKERS:
            return

        tracked = getattr(self.tracker, TRACKERS[event_type])(event, data)
        rules.run(event_type, event, data, tracked, self.findings)

    def build_report(self, events: list[dict[str, Any]], skipped_lines: int) -> dict[str, Any]:
        for event in events:
            self.observe(event)
        section = None
        if self.static is not None:
            section = correlate.correlate(self.static, self.tracker)
            static_bridges.detect_static_unobserved(section, self.findings)
        return assemble.build_report(self.tracker, self.findings, events, skipped_lines, section)
