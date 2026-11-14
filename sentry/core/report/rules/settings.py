"""core/report/rules: findings for risky WebSettings values."""

from __future__ import annotations

from typing import Any

from core.report.findings import FindingStore
from core.report.rules.catalog import DANGEROUS_SETTINGS
from core.report.values import normalize_value, parse_bool


def detect_setting_changed(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    setting = tracked["setting"]
    value = tracked["value"]

    if setting == "setMixedContentMode" and normalize_value(value) == 0:
        findings.add(
            "WV-MIXED-CONTENT",
            "high",
            "Mixed content is always allowed",
            "The WebView allows HTTPS pages to load cleartext HTTP subresources, weakening transport security.",
            "Use MIXED_CONTENT_NEVER_ALLOW unless a documented legacy compatibility case exists.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "setting": setting, "value": value},
            f"WV-MIXED-CONTENT:{data.get('webViewId')}",
        )
        return

    rule = DANGEROUS_SETTINGS.get(str(setting))
    if not rule:
        return

    expected, severity, rule_id, title, description, recommendation = rule
    observed = parse_bool(value)
    if observed is expected:
        findings.add(
            rule_id,
            severity,
            title,
            description,
            recommendation,
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "setting": setting, "value": value},
            f"{rule_id}:{data.get('webViewId')}",
        )
