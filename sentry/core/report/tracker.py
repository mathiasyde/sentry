"""core/report: per-WebView state built from events (inventory, bridges, calls, taint flows); never creates findings."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.report.urls import normalize_trusted_origin, url_origin
from core.report.values import first_arg

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


class WebViewTracker:
    def __init__(self, trusted_origins: set[str]) -> None:
        self.trusted_origins = {
            normalize_trusted_origin(origin) for origin in trusted_origins
        }
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

    def webview(self, webview_id: Any) -> dict[str, Any]:
        return self.webviews[str(webview_id or "unknown")]

    def track_url(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        webview = self.webview(data.get("webViewId"))
        url = data.get("url") or data.get("baseUrl") or data.get("historyUrl")
        source = data.get("source")

        if url:
            webview["urls"].append(url)
            origin = url_origin(url)
            if origin and origin not in webview["origins"]:
                webview["origins"].append(origin)

        return {"tracker": self, "url": url, "source": source}

    def track_setting(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        webview = self.webview(data.get("webViewId"))
        setting = data.get("setting")
        value = first_arg(data)
        webview["settings"][setting] = value

        return {"tracker": self, "setting": setting, "value": value}

    def track_bridge_added(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
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

        return {"tracker": self, "interface_name": interface_name, "page_url": page_url, "origin": origin, "trusted": trusted}

    def track_bridge_method(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        webview = self.webview(data.get("webViewId"))
        method = str(data.get("method") or "")
        method_event = dict(data)
        method_event["timestamp"] = event.get("timestamp")
        method_event["origin"] = data.get("origin") or url_origin(data.get("pageUrl"))
        webview["bridge_methods"].append(method_event)

        return {"tracker": self, "method": method}

    def track_bridge_call(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
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

        return {
            "tracker": self,
            "page_url": page_url,
            "current_origin": current_origin,
            "attached_origin": attached_origin,
            "method": method,
        }

    def track_js_probe(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
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

        flow = None
        sink_url = None
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

        return {
            "tracker": self,
            "name": name,
            "args": args,
            "href": href,
            "taints": taints,
            "sink_url": sink_url,
            "flow": flow,
        }

    def track_untracked(self, event: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        """Event types that update no WebView state (and must not create a WebView entry)."""
        return {"tracker": self}

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
