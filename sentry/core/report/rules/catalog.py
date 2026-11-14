"""core/report/rules: rule data: severities, scoring, risky WebView settings and sensitive-name patterns."""

from __future__ import annotations

import re

SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}

SEVERITY_SCORE = {
    "critical": 40,
    "high": 20,
    "medium": 10,
    "low": 3,
    "info": 0,
}

DANGEROUS_SETTINGS = {
    "setJavaScriptEnabled": (
        True,
        "medium",
        "WV-JS-ENABLED",
        "JavaScript execution is enabled",
        "JavaScript is enabled in a WebView. This is expected for hybrid apps, but it increases the impact of untrusted content, XSS, and exposed JavaScript bridges.",
        "Only enable JavaScript for trusted content and pair it with strict origin checks before exposing native bridges.",
    ),
    "setAllowFileAccess": (
        True,
        "medium",
        "WV-FILE-ACCESS",
        "File access is enabled",
        "The WebView can access local files. Combined with file URLs, content injection, or permissive bridge methods, this can expose app-private data.",
        "Disable file access unless the app has a specific local-content use case.",
    ),
    "setAllowContentAccess": (
        True,
        "low",
        "WV-CONTENT-ACCESS",
        "Content provider access is enabled",
        "The WebView can load content:// resources. This can become risky when untrusted content can influence loaded URLs.",
        "Disable content access unless required and validate all content:// URLs before loading them.",
    ),
    "setAllowFileAccessFromFileURLs": (
        True,
        "high",
        "WV-FILE-FROM-FILE",
        "File URLs can access other file URLs",
        "A page loaded from file:// can read other file:// resources, which can expose local app or device files.",
        "Keep allowFileAccessFromFileURLs disabled and avoid loading untrusted file:// pages.",
    ),
    "setAllowUniversalAccessFromFileURLs": (
        True,
        "critical",
        "WV-UNIVERSAL-FILE-ACCESS",
        "File URLs can access arbitrary origins",
        "A file:// page can make network requests to arbitrary origins. This is a high-impact WebView misconfiguration.",
        "Keep allowUniversalAccessFromFileURLs disabled and serve local content from a constrained WebViewAssetLoader origin when possible.",
    ),
    "setSafeBrowsingEnabled": (
        False,
        "medium",
        "WV-SAFE-BROWSING-DISABLED",
        "Safe Browsing is disabled",
        "WebView Safe Browsing was disabled, reducing protection against known malicious URLs.",
        "Leave Safe Browsing enabled unless there is a documented compatibility reason.",
    ),
    "setGeolocationEnabled": (
        True,
        "low",
        "WV-GEOLOCATION-ENABLED",
        "Geolocation is enabled",
        "Geolocation support is enabled in WebView content.",
        "Only allow geolocation for trusted origins and ensure prompts are not auto-approved.",
    ),
    "setJavaScriptCanOpenWindowsAutomatically": (
        True,
        "low",
        "WV-JS-POPUPS",
        "JavaScript can open windows automatically",
        "JavaScript is allowed to open windows without user gestures, which can enable unwanted navigation flows.",
        "Disable automatic window opening unless required by trusted content.",
    ),
}

SENSITIVE_METHOD_RE = re.compile(
    r"(camera|photo|image|location|gps|contact|sms|phone|call|record|audio|"
    r"microphone|mic|token|secret|password|cookie|session|credential|permission|"
    r"file|read|write|delete|download|upload|device|imei|androidid|id)",
    re.IGNORECASE,
)

NETWORK_JS_EVENTS = {"fetch", "XMLHttpRequest.open"}
