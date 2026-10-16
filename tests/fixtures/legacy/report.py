#!/usr/bin/env python3
"""Generate WebView security findings from Sentry JSON event logs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
TAINT_SINK_EVENTS = {
    "fetch",
    "XMLHttpRequest.open",
    "XMLHttpRequest.send",
    "navigator.sendBeacon",
    "window.postMessage",
    "window.open",
    "location.assign",
    "location.replace",
    "eval",
    "localStorage.setItem",
}


def normalize_value(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1:
        return normalize_value(value[0])
    return value


def parse_bool(value: Any) -> bool | None:
    value = normalize_value(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def first_arg(data: dict[str, Any]) -> Any:
    args = data.get("args")
    if isinstance(args, list) and args:
        return args[0]
    return None


def url_origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    if parsed.scheme in {"file", "data", "about", "javascript"}:
        return parsed.scheme + ":"
    if not parsed.netloc:
        return parsed.scheme + ":"
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_trusted_origin(origin: str) -> str:
    return url_origin(origin) or origin.rstrip("/")


def is_remote_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme in {"http", "https"})


def is_cleartext_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "http")


def is_local_file_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "file")


def is_data_url(url: str | None) -> bool:
    return bool(url and urlparse(url).scheme == "data")


def is_trusted(url: str | None, trusted_origins: set[str]) -> bool:
    if not trusted_origins:
        return False
    origin = url_origin(url)
    return bool(origin and origin in trusted_origins)


def compact(value: Any, max_length: int = 240) -> Any:
    if isinstance(value, str) and len(value) > max_length:
        return value[: max_length - 3] + "..."
    if isinstance(value, list):
        return [compact(item, max_length) for item in value[:10]]
    if isinstance(value, dict):
        return {key: compact(val, max_length) for key, val in value.items()}
    return value


def load_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    skipped = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue

            start = raw.find("{")
            if start < 0:
                skipped += 1
                continue

            try:
                event = json.loads(raw[start:])
            except json.JSONDecodeError:
                skipped += 1
                continue

            if isinstance(event, dict) and "type" in event:
                events.append(event)
            else:
                skipped += 1

    return events, skipped


class Analyzer:
    def __init__(self, trusted_origins: set[str]) -> None:
        self.trusted_origins = {
            normalize_trusted_origin(origin) for origin in trusted_origins
        }
        self.findings: dict[str, dict[str, Any]] = {}
        self.webviews: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "urls": [],
                "origins": [],
                "settings": {},
                "bridges": {},
                "bridge_exposures": [],
                "bridge_methods": [],
                "bridge_calls": [],
                "taint_sources": [],
                "taint_flows": [],
                "permissions": [],
                "js_events": [],
            }
        )

    def add_finding(
        self,
        rule_id: str,
        severity: str,
        title: str,
        description: str,
        recommendation: str,
        evidence: dict[str, Any],
        fingerprint: str | None = None,
    ) -> None:
        key = fingerprint or f"{rule_id}:{json.dumps(evidence, sort_keys=True, default=str)}"
        finding = self.findings.get(key)
        if finding is None:
            self.findings[key] = {
                "rule_id": rule_id,
                "severity": severity,
                "title": title,
                "description": description,
                "recommendation": recommendation,
                "evidence": [],
            }
            finding = self.findings[key]

        if len(finding["evidence"]) < 20:
            finding["evidence"].append(compact(evidence))

    def webview(self, webview_id: Any) -> dict[str, Any]:
        return self.webviews[str(webview_id or "unknown")]

    def observe(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if event_type == "url.loaded":
            self.observe_url(event, data)
        elif event_type == "webview.settings.changed":
            self.observe_setting(event, data)
        elif event_type == "bridge.added":
            self.observe_bridge_added(event, data)
        elif event_type == "bridge.method.added":
            self.observe_bridge_method(event, data)
        elif event_type == "bridge.method.called":
            self.observe_bridge_call(event, data)
        elif event_type == "permission.requested":
            self.observe_permission_request(event, data)
        elif event_type == "permission.grant.called":
            self.observe_permission_grant(event, data)
        elif event_type == "js.evaluated":
            self.observe_js_eval(event, data)
        elif event_type == "js.probe":
            self.observe_js_probe(event, data)
        elif event_type == "js.probe.error":
            self.observe_probe_error(event, data)

    def observe_url(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        url = data.get("url") or data.get("baseUrl") or data.get("historyUrl")
        source = data.get("source")

        if url:
            webview["urls"].append(url)
            origin = url_origin(url)
            if origin and origin not in webview["origins"]:
                webview["origins"].append(origin)

        if is_cleartext_url(url):
            self.add_finding(
                "WV-CLEARTEXT-URL",
                "high",
                "Cleartext HTTP content loaded in WebView",
                "The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.",
                "Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.",
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "url": url, "source": source},
                f"WV-CLEARTEXT-URL:{data.get('webViewId')}:{url}",
            )

        if is_local_file_url(url):
            self.add_finding(
                "WV-FILE-URL-LOADED",
                "high",
                "file:// content loaded in WebView",
                "The WebView loaded local file content. file:// pages are risky when file access or JavaScript bridges are enabled.",
                "Avoid file:// content for untrusted pages. Prefer WebViewAssetLoader or a tightly controlled HTTPS origin.",
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "url": url, "source": source},
                f"WV-FILE-URL-LOADED:{data.get('webViewId')}:{url}",
            )

        if is_data_url(url) or source in {"loadData", "loadDataWithBaseURL"}:
            self.add_finding(
                "WV-INLINE-CONTENT",
                "medium",
                "Inline HTML content loaded in WebView",
                "The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.",
                "Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.",
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "source": source, "url": url},
                f"WV-INLINE-CONTENT:{data.get('webViewId')}:{source}:{url}",
            )

    def observe_setting(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        setting = data.get("setting")
        value = first_arg(data)
        webview["settings"][setting] = value

        if setting == "setMixedContentMode" and normalize_value(value) == 0:
            self.add_finding(
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
            self.add_finding(
                rule_id,
                severity,
                title,
                description,
                recommendation,
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "setting": setting, "value": value},
                f"{rule_id}:{data.get('webViewId')}",
            )

    def observe_bridge_added(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        interface_name = data.get("interfaceName")
        page_url = (
            data.get("attachedPageUrl")
            or data.get("pageUrl")
            or self.latest_url(webview)
        )
        origin = data.get("attachedOrigin") or data.get("origin") or url_origin(page_url)
        trusted = bool(origin and origin in self.trusted_origins)

        webview["bridges"][interface_name] = {
            "className": data.get("className"),
            "pageUrl": page_url,
            "origin": origin,
            "trusted": trusted,
        }
        webview["bridge_exposures"].append(
            {
                "timestamp": event.get("timestamp"),
                "interfaceName": interface_name,
                "className": data.get("className"),
                "pageUrl": page_url,
                "origin": origin,
                "trusted": trusted,
            }
        )

        severity = "high" if is_remote_url(page_url) and not trusted else "medium"
        self.add_finding(
            "WV-JS-BRIDGE-EXPOSED",
            severity,
            "JavaScript bridge exposed to WebView content",
            "A native object was exposed to JavaScript through addJavascriptInterface. Any page that can run JavaScript in this WebView can attempt to call annotated public methods.",
            "Expose bridges only to trusted origins, remove the bridge before loading untrusted content, and enforce origin checks in every sensitive method.",
            {
                "timestamp": event.get("timestamp"),
                "webViewId": data.get("webViewId"),
                "interfaceName": interface_name,
                "className": data.get("className"),
                "pageUrl": page_url,
                "origin": origin,
                "trusted": trusted,
            },
            f"WV-JS-BRIDGE-EXPOSED:{data.get('webViewId')}:{interface_name}",
        )

    def observe_bridge_method(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        method = str(data.get("method") or "")
        method_event = dict(data)
        method_event["timestamp"] = event.get("timestamp")
        method_event["origin"] = data.get("origin") or url_origin(data.get("pageUrl"))
        webview["bridge_methods"].append(method_event)

        if SENSITIVE_METHOD_RE.search(method):
            self.add_finding(
                "WV-SENSITIVE-BRIDGE-METHOD",
                "high",
                "Sensitive-looking JavaScript bridge method exposed",
                "A JavaScript bridge exposes a method whose name suggests access to sensitive data, permissions, files, device identifiers, or device capabilities.",
                "Audit the method implementation, require trusted-origin checks, and avoid returning sensitive native data directly to JavaScript.",
                {
                    "timestamp": event.get("timestamp"),
                    "webViewId": data.get("webViewId"),
                    "interfaceName": data.get("interfaceName"),
                    "className": data.get("className"),
                    "method": method,
                    "args": data.get("args"),
                },
                f"WV-SENSITIVE-BRIDGE-METHOD:{data.get('webViewId')}:{data.get('interfaceName')}:{method}",
            )

    def observe_bridge_call(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        page_url = (
            data.get("currentPageUrl")
            or data.get("pageUrl")
            or self.latest_url(webview)
        )
        current_origin = data.get("currentOrigin") or url_origin(page_url)
        attached_origin = data.get("attachedOrigin")
        method = data.get("methodName")
        call_event = dict(data)
        call_event["timestamp"] = event.get("timestamp")
        call_event["pageUrl"] = page_url
        call_event["currentOrigin"] = current_origin
        call_event["attachedOrigin"] = attached_origin
        webview["bridge_calls"].append(call_event)

        if is_remote_url(page_url) and not is_trusted(page_url, self.trusted_origins):
            self.add_finding(
                "WV-BRIDGE-CALLED-BY-REMOTE-CONTENT",
                "high",
                "Remote WebView content called a native bridge method",
                "Remote content invoked a native JavaScript bridge method. This is a direct native attack surface from web content.",
                "Restrict bridge calls to trusted origins and validate authorization inside the bridge method before performing native actions.",
                {
                    "timestamp": event.get("timestamp"),
                    "webViewId": data.get("webViewId"),
                    "pageUrl": page_url,
                    "currentOrigin": current_origin,
                    "attachedOrigin": attached_origin,
                    "interfaceName": data.get("interfaceName"),
                    "methodName": method,
                    "args": data.get("args"),
                    "retval": data.get("retval"),
                    "error": data.get("error"),
                },
                f"WV-BRIDGE-CALLED-BY-REMOTE-CONTENT:{data.get('webViewId')}:{page_url}:{method}",
            )

    def observe_permission_request(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        origin = data.get("origin")
        severity = "medium" if origin else "low"
        self.add_finding(
            "WV-WEB-PERMISSION-REQUEST",
            severity,
            "WebView content requested a browser permission",
            "Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.",
            "Grant WebView permissions only after validating the request origin and the exact requested resources.",
            {"timestamp": event.get("timestamp"), "origin": origin, "resources": data.get("resources"), "type": data.get("type")},
            f"WV-WEB-PERMISSION-REQUEST:{origin}:{data.get('resources')}:{data.get('type')}",
        )

    def observe_permission_grant(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        origin = data.get("origin")
        severity = "high" if origin and not str(origin).startswith("https://") else "medium"
        self.add_finding(
            "WV-WEB-PERMISSION-GRANTED",
            severity,
            "WebView permission was granted to web content",
            "A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.",
            "Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.",
            {"timestamp": event.get("timestamp"), "origin": origin, "resources": data.get("resources")},
            f"WV-WEB-PERMISSION-GRANTED:{origin}:{data.get('resources')}",
        )

    def observe_js_eval(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        script = data.get("script")
        self.add_finding(
            "WV-JS-EVALUATED",
            "medium",
            "Native code evaluated JavaScript in WebView",
            "The app called evaluateJavascript. If script contents include attacker-controlled data, this can become JavaScript injection.",
            "Avoid string-built JavaScript. Use structured message passing and encode any values inserted into JavaScript code.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "pageUrl": data.get("pageUrl"), "script": script},
            f"WV-JS-EVALUATED:{data.get('webViewId')}:{script}",
        )

    def observe_js_probe(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        webview = self.webview(data.get("webViewId"))
        name = data.get("name")
        args = data.get("arguments")
        href = data.get("href")
        webview["js_events"].append(data)
        taints = data.get("taints") if isinstance(data.get("taints"), list) else []

        if name == "bridge.method.return.tainted":
            source = taints[0].get("source") if taints and isinstance(taints[0], dict) else {}
            taint_source = {
                "timestamp": event.get("timestamp"),
                "webViewId": data.get("webViewId"),
                "href": href,
                "bridge": data.get("bridge"),
                "source": source,
                "valuePreview": taints[0].get("valuePreview") if taints else None,
            }
            webview["taint_sources"].append(taint_source)

        if taints and name in TAINT_SINK_EVENTS:
            sink_url = self.extract_js_network_url(name, args)
            flow = {
                "timestamp": event.get("timestamp"),
                "webViewId": data.get("webViewId"),
                "href": href,
                "sink": name,
                "sinkUrl": sink_url,
                "arguments": args,
                "taints": taints,
            }
            webview["taint_flows"].append(flow)

            self.add_finding(
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
            url = self.extract_js_network_url(name, args)
            if url and is_cleartext_url(url):
                self.add_finding(
                    "WV-JS-CLEARTEXT-NETWORK",
                    "medium",
                    "WebView JavaScript contacted a cleartext URL",
                    "JavaScript running inside the WebView made or prepared a cleartext HTTP request.",
                    "Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.",
                    {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": href, "api": name, "url": url},
                    f"WV-JS-CLEARTEXT-NETWORK:{data.get('webViewId')}:{url}",
                )

        if name == "eval":
            self.add_finding(
                "WV-JS-EVAL",
                "medium",
                "WebView page executed JavaScript eval",
                "JavaScript running inside the WebView called eval, which increases XSS and injection impact.",
                "Avoid eval and use safer parsing or dispatch mechanisms.",
                {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": href, "arguments": args},
                f"WV-JS-EVAL:{data.get('webViewId')}:{href}",
            )

    def observe_probe_error(self, event: dict[str, Any], data: dict[str, Any]) -> None:
        self.add_finding(
            "WV-PROBE-ERROR",
            "info",
            "JavaScript probe reported an error",
            "The injected JavaScript probe could not run or parse its result for at least one WebView state.",
            "Review whether the page navigated, blocked script execution, or removed probe state.",
            {"timestamp": event.get("timestamp"), "webViewId": data.get("webViewId"), "href": data.get("href"), "error": data.get("error")},
            f"WV-PROBE-ERROR:{data.get('webViewId')}:{data.get('href')}:{data.get('error')}",
        )

    def latest_url(self, webview: dict[str, Any]) -> str | None:
        urls = webview.get("urls") or []
        return urls[-1] if urls else None

    def extract_js_network_url(self, name: str, args: Any) -> str | None:
        if not isinstance(args, list) or not args:
            return None
        if name == "fetch":
            first = args[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url")
        if name in {"navigator.sendBeacon", "window.open", "location.assign", "location.replace"}:
            return args[0] if isinstance(args[0], str) else None
        if name == "window.postMessage" and len(args) >= 2:
            return args[1] if isinstance(args[1], str) else None
        if name == "XMLHttpRequest.open" and len(args) >= 2:
            return args[1] if isinstance(args[1], str) else None
        return None

    def build_report(self, events: list[dict[str, Any]], skipped_lines: int) -> dict[str, Any]:
        for event in events:
            self.observe(event)

        findings = sorted(
            self.findings.values(),
            key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["rule_id"], item["title"]),
        )
        counts = Counter(finding["severity"] for finding in findings)
        risk_score = min(
            100,
            sum(SEVERITY_SCORE[finding["severity"]] for finding in findings),
        )

        return {
            "summary": {
                "risk_score": risk_score,
                "event_count": len(events),
                "skipped_line_count": skipped_lines,
                "finding_count": len(findings),
                "severity_counts": {severity: counts.get(severity, 0) for severity in SEVERITY_ORDER},
                "webview_count": len(self.webviews),
                "trusted_origins": sorted(self.trusted_origins),
            },
            "findings": findings,
            "webviews": self.render_webviews(),
            "origin_bridge_map": self.render_origin_bridge_map(),
        }

    def render_webviews(self) -> dict[str, Any]:
        rendered = {}
        for webview_id, state in self.webviews.items():
            rendered[webview_id] = {
                "urls": state["urls"],
                "origins": state["origins"],
                "settings": state["settings"],
                "bridges": state["bridges"],
                "bridge_exposure_count": len(state["bridge_exposures"]),
                "bridge_method_count": len(state["bridge_methods"]),
                "bridge_call_count": len(state["bridge_calls"]),
                "taint_source_count": len(state["taint_sources"]),
                "taint_flow_count": len(state["taint_flows"]),
                "taint_flows": state["taint_flows"],
                "permission_event_count": len(state["permissions"]),
                "js_event_count": len(state["js_events"]),
            }
        return rendered

    def render_origin_bridge_map(self) -> dict[str, Any]:
        rendered: dict[str, Any] = {}

        for webview_id, state in self.webviews.items():
            origins: dict[str, dict[str, Any]] = {}

            for exposure in state["bridge_exposures"]:
                origin = exposure.get("origin") or "unknown"
                entry = origins.setdefault(
                    origin,
                    {
                        "trusted": bool(origin in self.trusted_origins),
                        "remote": origin.startswith("http://")
                        or origin.startswith("https://"),
                        "page_urls": [],
                        "bridges": {},
                    },
                )
                page_url = exposure.get("pageUrl")
                if page_url and page_url not in entry["page_urls"]:
                    entry["page_urls"].append(page_url)

                interface_name = exposure.get("interfaceName") or "unknown"
                bridge = entry["bridges"].setdefault(
                    interface_name,
                    {
                        "interfaceName": interface_name,
                        "className": exposure.get("className"),
                        "attachedPageUrl": page_url,
                        "attachedOrigin": exposure.get("origin"),
                        "methods": [],
                        "calls": [],
                    },
                )
                bridge["className"] = bridge["className"] or exposure.get("className")

            for method in state["bridge_methods"]:
                interface_name = method.get("interfaceName") or "unknown"
                matching_origins = [
                    origin
                    for origin, entry in origins.items()
                    if interface_name in entry["bridges"]
                ] or ["unknown"]

                for origin in matching_origins:
                    entry = origins.setdefault(
                        origin,
                        {
                            "trusted": bool(origin in self.trusted_origins),
                            "remote": origin.startswith("http://")
                            or origin.startswith("https://"),
                            "page_urls": [],
                            "bridges": {},
                        },
                    )
                    bridge = entry["bridges"].setdefault(
                        interface_name,
                        {
                            "interfaceName": interface_name,
                            "className": method.get("className"),
                            "attachedPageUrl": None,
                            "attachedOrigin": origin if origin != "unknown" else None,
                            "methods": [],
                            "calls": [],
                        },
                    )
                    method_name = method.get("method")
                    if method_name and method_name not in bridge["methods"]:
                        bridge["methods"].append(method_name)

            for call in state["bridge_calls"]:
                origin = call.get("currentOrigin") or call.get("attachedOrigin") or "unknown"
                entry = origins.setdefault(
                    origin,
                    {
                        "trusted": bool(origin in self.trusted_origins),
                        "remote": origin.startswith("http://")
                        or origin.startswith("https://"),
                        "page_urls": [],
                        "bridges": {},
                    },
                )
                page_url = call.get("pageUrl") or call.get("currentPageUrl")
                if page_url and page_url not in entry["page_urls"]:
                    entry["page_urls"].append(page_url)

                interface_name = call.get("interfaceName") or "unknown"
                bridge = entry["bridges"].setdefault(
                    interface_name,
                    {
                        "interfaceName": interface_name,
                        "className": call.get("className"),
                        "attachedPageUrl": call.get("attachedPageUrl"),
                        "attachedOrigin": call.get("attachedOrigin"),
                        "methods": [],
                        "calls": [],
                    },
                )
                call_summary = {
                    "timestamp": call.get("timestamp"),
                    "methodName": call.get("methodName"),
                    "pageUrl": page_url,
                    "currentOrigin": call.get("currentOrigin"),
                    "attachedOrigin": call.get("attachedOrigin"),
                    "args": compact(call.get("args")),
                    "retval": compact(call.get("retval")),
                    "error": call.get("error"),
                }
                bridge["calls"].append(call_summary)
                method_name = call.get("methodName")
                if method_name and method_name not in bridge["methods"]:
                    bridge["methods"].append(method_name)

            rendered[webview_id] = {
                "origins": {
                    origin: {
                        **entry,
                        "bridges": list(entry["bridges"].values()),
                    }
                    for origin, entry in sorted(origins.items())
                }
            }

        return rendered


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Sentry WebView Security Report",
        "",
        "## Summary",
        "",
        f"- Risk score: {summary['risk_score']}/100",
        f"- Events analyzed: {summary['event_count']}",
        f"- Findings: {summary['finding_count']}",
        f"- WebViews observed: {summary['webview_count']}",
        f"- Skipped non-event lines: {summary['skipped_line_count']}",
        "",
        "## Severity Counts",
        "",
    ]

    for severity in ["critical", "high", "medium", "low", "info"]:
        lines.append(f"- {severity.title()}: {summary['severity_counts'].get(severity, 0)}")

    lines.extend(["", "## Findings", ""])

    if not report["findings"]:
        lines.append("No findings were generated from the provided log.")
    else:
        for index, finding in enumerate(report["findings"], start=1):
            lines.extend(
                [
                    f"### {index}. [{finding['severity'].upper()}] {finding['title']}",
                    "",
                    f"- Rule: `{finding['rule_id']}`",
                    f"- Description: {finding['description']}",
                    f"- Recommendation: {finding['recommendation']}",
                    "- Evidence:",
                ]
            )
            for evidence in finding["evidence"]:
                lines.append(f"  - `{json.dumps(evidence, sort_keys=True, default=str)}`")
            lines.append("")

    lines.extend(["", "## WebView Inventory", ""])
    if not report["webviews"]:
        lines.append("No WebView activity was observed.")
    else:
        for webview_id, state in sorted(report["webviews"].items()):
            lines.extend(
                [
                    f"### WebView {webview_id}",
                    "",
                    f"- URLs observed: {len(state['urls'])}",
                    f"- Settings observed: {len(state['settings'])}",
                    f"- Bridges observed: {len(state['bridges'])}",
                    f"- Bridge methods observed: {state['bridge_method_count']}",
                    f"- Bridge calls observed: {state['bridge_call_count']}",
                    f"- JavaScript events observed: {state['js_event_count']}",
                ]
            )
            if state["urls"]:
                lines.append("- Recent URLs:")
                for url in state["urls"][-5:]:
                    lines.append(f"  - `{url}`")
            lines.append("")

    lines.extend(["", "## Sensitive Data Flows", ""])
    any_taint_flow = False
    for webview_id, state in sorted(report["webviews"].items()):
        flows = state.get("taint_flows") or []
        if not flows:
            continue

        any_taint_flow = True
        lines.extend([f"### WebView {webview_id}", ""])
        for flow in flows:
            lines.extend(
                [
                    f"- Sink: `{flow.get('sink')}`",
                    f"  - Page: `{flow.get('href')}`",
                ]
            )
            if flow.get("sinkUrl"):
                lines.append(f"  - Destination: `{flow.get('sinkUrl')}`")
            for taint in flow.get("taints") or []:
                source = taint.get("source") if isinstance(taint, dict) else {}
                if not isinstance(source, dict):
                    source = {}
                lines.append(
                    "  - Source: "
                    f"`{source.get('interfaceName')}.{source.get('methodName')}` "
                    f"({source.get('className') or 'unknown class'})"
                )
                if taint.get("valuePreview"):
                    lines.append(f"  - Value preview: `{taint.get('valuePreview')}`")
        lines.append("")

    if not any_taint_flow:
        lines.append("No sensitive bridge-return values were observed reaching JavaScript sinks.")

    lines.extend(["", "## Origin To Bridge Map", ""])
    origin_bridge_map = report.get("origin_bridge_map") or {}
    if not origin_bridge_map:
        lines.append("No JavaScript bridge origins were observed.")
    else:
        for webview_id, webview_map in sorted(origin_bridge_map.items()):
            lines.extend([f"### WebView {webview_id}", ""])
            origins = webview_map.get("origins") or {}
            if not origins:
                lines.append("No JavaScript bridge origins were observed for this WebView.")
                lines.append("")
                continue

            for origin, origin_entry in sorted(origins.items()):
                trust = "trusted" if origin_entry.get("trusted") else "untrusted"
                remote = "remote" if origin_entry.get("remote") else "local"
                lines.extend(
                    [
                        f"#### `{origin}`",
                        "",
                        f"- Classification: {trust}, {remote}",
                    ]
                )

                page_urls = origin_entry.get("page_urls") or []
                if page_urls:
                    lines.append("- Page URLs:")
                    for page_url in page_urls[-5:]:
                        lines.append(f"  - `{page_url}`")

                bridges = origin_entry.get("bridges") or []
                if bridges:
                    lines.append("- Bridges:")
                    for bridge in bridges:
                        methods = bridge.get("methods") or []
                        calls = bridge.get("calls") or []
                        lines.append(
                            "  - "
                            f"`{bridge.get('interfaceName')}` "
                            f"({bridge.get('className') or 'unknown class'}): "
                            f"{len(methods)} methods, {len(calls)} calls"
                        )
                        if methods:
                            lines.append(
                                "    - Methods: "
                                + ", ".join(f"`{method}`" for method in methods[:12])
                            )
                        for call in calls[:5]:
                            lines.append(
                                "    - Call: "
                                f"`{call.get('methodName')}` at "
                                f"`{call.get('pageUrl')}`"
                            )
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate WebView security findings from Sentry JSON logs.",
    )
    parser.add_argument("log_file", type=Path, help="Path to the Sentry output log.")
    parser.add_argument(
        "--json",
        dest="json_output",
        type=Path,
        default=Path("target/report.json"),
        help="Path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--markdown",
        dest="markdown_output",
        type=Path,
        default=Path("logs/report.md"),
        help="Path for the Markdown report.",
    )
    parser.add_argument(
        "--trusted-origin",
        action="append",
        default=[],
        help="Trusted WebView origin, for example https://app.example.com. Can be repeated.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    events, skipped = load_events(args.log_file)
    analyzer = Analyzer(set(args.trusted_origin))
    report = analyzer.build_report(events, skipped)

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)

    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")

    print(
        "Generated report: "
        f"{args.json_output} and {args.markdown_output} "
        f"({report['summary']['finding_count']} findings, "
        f"risk score {report['summary']['risk_score']}/100)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
