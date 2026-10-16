"""core/report: assemble the machine-readable report (summary, WebView inventory, origin-to-bridge map)."""

from __future__ import annotations

from typing import Any

from core.report.values import compact


def build_report(
    tracker: Any, findings: Any, events: list[dict[str, Any]], skipped_lines: int, static_section: dict[str, Any] | None = None
) -> dict[str, Any]:
    sorted_findings = findings.sorted_findings()

    report = {
        "summary": {
            "risk_score": findings.risk_score(),
            "event_count": len(events),
            "skipped_line_count": skipped_lines,
            "finding_count": len(sorted_findings),
            "severity_counts": findings.severity_counts(),
            "webview_count": len(tracker.webviews),
            "trusted_origins": sorted(tracker.trusted_origins),
        },
        "findings": sorted_findings,
        "webviews": render_webviews(tracker),
        "origin_bridge_map": render_origin_bridge_map(tracker),
    }
    if static_section is not None:
        report["static_bridges"] = static_section
    return report


def render_webviews(tracker: Any) -> dict[str, Any]:
    rendered = {}
    for webview_id, state in tracker.webviews.items():
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


def render_origin_bridge_map(tracker: Any) -> dict[str, Any]:
    rendered: dict[str, Any] = {}

    for webview_id, state in tracker.webviews.items():
        origins: dict[str, dict[str, Any]] = {}

        for exposure in state["bridge_exposures"]:
            origin = exposure.get("origin") or "unknown"
            entry = origins.setdefault(
                origin,
                {
                    "trusted": bool(origin in tracker.trusted_origins),
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
                        "trusted": bool(origin in tracker.trusted_origins),
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
                    "trusted": bool(origin in tracker.trusted_origins),
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
