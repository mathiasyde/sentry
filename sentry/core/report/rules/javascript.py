"""core/report/rules: findings for evaluated JavaScript, page-side probe events and probe errors."""

from __future__ import annotations

import json
from typing import Any

from core.report.findings import FindingStore
from core.report.rules.catalog import NETWORK_JS_EVENTS
from core.report.urls import is_cleartext_url


def detect_js_evaluated(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    script = data.get("script")
    findings.add(
        "WV-JS-EVALUATED",
        "medium",
        "Native code evaluated JavaScript in WebView",
        "The app called evaluateJavascript. If script contents include attacker-controlled data, this can become JavaScript injection.",
        "Avoid string-built JavaScript. Use structured message passing and encode any values inserted into JavaScript code.",
        {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "pageUrl": data.get("pageUrl"), "script": script},
        f"WV-JS-EVALUATED:{data.get('webViewId')}:{script}",
    )


def detect_js_probe(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    tracker = tracked["tracker"]
    name = tracked["name"]
    args = tracked["args"]
    href = tracked["href"]
    taints = tracked["taints"]

    if tracked["flow"] is not None:
        sink_url = tracked["sink_url"]
        findings.add(
            "WV-TAINTED-BRIDGE-DATA-TO-JS-SINK",
            "critical",
            "Sensitive native bridge data reached a JavaScript sink",
            "A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.",
            "Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.",
            {
                "timestamp": event.get("timestamp"),
                "webViewId": data.get("webViewId"),
                "href": href,
                "sink": name,
                "sinkUrl": sink_url,
                "taints": taints,
                "arguments": args,
            },
            f"WV-TAINTED-BRIDGE-DATA-TO-JS-SINK:{data.get('webViewId')}:{href}:{name}:{sink_url}:{json.dumps(taints, sort_keys=True, default=str)}",
        )

    if name in NETWORK_JS_EVENTS:
        url = tracker.extract_js_network_url(name, args)
        if url and is_cleartext_url(url):
            findings.add(
                "WV-JS-CLEARTEXT-NETWORK",
                "medium",
                "WebView JavaScript contacted a cleartext URL",
                "JavaScript running inside the WebView made or prepared a cleartext HTTP request.",
                "Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.",
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": href, "api": name, "url": url},
                f"WV-JS-CLEARTEXT-NETWORK:{data.get('webViewId')}:{url}",
            )

    if name == "eval":
        findings.add(
            "WV-JS-EVAL",
            "medium",
            "WebView page executed JavaScript eval",
            "JavaScript running inside the WebView called eval, which increases XSS and injection impact.",
            "Avoid eval and use safer parsing or dispatch mechanisms.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": href, "arguments": args},
            f"WV-JS-EVAL:{data.get('webViewId')}:{href}",
        )


def detect_probe_error(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    findings.add(
        "WV-PROBE-ERROR",
        "info",
        "JavaScript probe reported an error",
        "The injected JavaScript probe could not run or parse its result for at least one WebView state.",
        "Review whether the page navigated, blocked script execution, or removed probe state.",
        {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": data.get("href"), "error": data.get("error")},
        f"WV-PROBE-ERROR:{data.get('webViewId')}:{data.get('href')}:{data.get('error')}",
    )
