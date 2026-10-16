"""core/report: render a report dict as the human-readable Markdown report."""

from __future__ import annotations

import json
from typing import Any

from core.report.markdown_static import static_section


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

    if report.get("static_bridges") is not None:
        lines.extend(static_section(report["static_bridges"]))

    return "\n".join(lines).rstrip() + "\n"
