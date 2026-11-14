"""core/report/rules: findings for JavaScript bridges found statically but never observed at runtime."""

from __future__ import annotations

from typing import Any

from core.report.findings import FindingStore


def detect_static_unobserved(section: dict[str, Any], findings: FindingStore) -> None:
    """Runs once per report on the correlated static section, not per event."""
    for bridge in section["bridges"]:
        if bridge["provenance"] != "static-only":
            continue
        static = bridge["static"]
        call_site = static["call_site"]
        name, class_name = bridge["interfaceName"], bridge["className"]
        findings.add(
            "WV-STATIC-BRIDGE-UNOBSERVED",
            "info",
            "JavaScript bridge found in the APK but not observed at runtime",
            "Static analysis found an addJavascriptInterface registration that the dynamic run never executed. "
            "The bridge is still part of the app's attack surface.",
            "Exercise the code path that registers this bridge (see call site) and review its exposed methods, "
            "especially those flagged sensitive.",
            {
                "interfaceName": name,
                "className": class_name,
                "nameStatus": static["name_status"],
                "classResolution": static["class_resolution"],
                "candidateClasses": static["candidate_classes"],
                "callSite": f"{call_site['class']}.{call_site['signature']}",
                "methods": [method["name"] for method in static["methods"]],
                "sensitiveMethods": bridge["sensitive_methods"],
            },
            f"WV-STATIC-BRIDGE-UNOBSERVED:{name or '?'}:{class_name or '?'}",
        )
