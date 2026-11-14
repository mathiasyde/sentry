"""core/report/rules: findings for WebView permission requests and grants."""

from __future__ import annotations

from typing import Any

from core.report.findings import FindingStore


def detect_permission_requested(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    origin = data.get("origin")
    severity = "medium" if origin else "low"
    findings.add(
        "WV-WEB-PERMISSION-REQUEST",
        severity,
        "WebView content requested a browser permission",
        "Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.",
        "Grant WebView permissions only after validating the request origin and the exact requested resources.",
        {"timestamp": event.get("timestamp"), "origin": origin, "resources": data.get("resources"), "type": data.get("type")},
        f"WV-WEB-PERMISSION-REQUEST:{origin}:{data.get('resources')}:{data.get('type')}",
    )


def detect_permission_granted(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    origin = data.get("origin")
    severity = "high" if origin and not str(origin).startswith("https://") else "medium"
    findings.add(
        "WV-WEB-PERMISSION-GRANTED",
        severity,
        "WebView permission was granted to web content",
        "A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.",
        "Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.",
        {"timestamp": event.get("timestamp"), "origin": origin, "resources": data.get("resources")},
        f"WV-WEB-PERMISSION-GRANTED:{origin}:{data.get('resources')}",
    )
