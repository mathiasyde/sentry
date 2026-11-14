"""core/report/rules: findings for exposed JavaScript bridges, sensitive bridge methods and remote bridge calls."""

from typing import Any

from core.report.findings import FindingStore
from core.report.rules.catalog import SENSITIVE_METHOD_RE
from core.report.urls import is_remote_url, is_trusted


def detect_bridge_added(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    interface_name = tracked["interface_name"]
    page_url = tracked["page_url"]
    origin = tracked["origin"]
    trusted = tracked["trusted"]

    severity = "high" if is_remote_url(page_url) and not trusted else "medium"
    findings.add(
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


def detect_bridge_method_added(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    method = tracked["method"]

    if SENSITIVE_METHOD_RE.search(method):
        findings.add(
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


def detect_bridge_method_called(event: dict[str, Any], data: dict[str, Any], tracked: dict[str, Any], findings: FindingStore) -> None:
    tracker = tracked["tracker"]
    page_url = tracked["page_url"]
    current_origin = tracked["current_origin"]
    attached_origin = tracked["attached_origin"]
    method = tracked["method"]

    if is_remote_url(page_url) and not is_trusted(page_url, tracker.trusted_origins):
        findings.add(
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
