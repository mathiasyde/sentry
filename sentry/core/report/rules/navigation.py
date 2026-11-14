"""core/report/rules: findings for loaded URLs (cleartext, file://, inline content)."""

from __future__ import annotations

from typing import Any

from core.report.findings import FindingStore
from core.report.urls import is_cleartext_url, is_data_url, is_local_file_url


def detect_url_loaded(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    url = tracked["url"]
    source = tracked["source"]

    if is_cleartext_url(url):
        findings.add(
            "WV-CLEARTEXT-URL",
            "high",
            "Cleartext HTTP content loaded in WebView",
            "The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.",
            "Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "url": url, "source": source},
            f"WV-CLEARTEXT-URL:{data.get('webViewId')}:{url}",
        )

    if is_local_file_url(url):
        findings.add(
            "WV-FILE-URL-LOADED",
            "high",
            "file:// content loaded in WebView",
            "The WebView loaded local file content. file:// pages are risky when file access or JavaScript bridges are enabled.",
            "Avoid file:// content for untrusted pages. Prefer WebViewAssetLoader or a tightly controlled HTTPS origin.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "url": url, "source": source},
            f"WV-FILE-URL-LOADED:{data.get('webViewId')}:{url}",
        )

    if is_data_url(url) or source in {"loadData", "loadDataWithBaseURL"}:
        findings.add(
            "WV-INLINE-CONTENT",
            "medium",
            "Inline HTML content loaded in WebView",
            "The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.",
            "Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "source": source, "url": url},
            f"WV-INLINE-CONTENT:{data.get('webViewId')}:{source}:{url}",
        )
