"""core/report: render the static bridge inventory section of the Markdown report."""

from __future__ import annotations

from typing import Any

PRE_17_NOTE = (
    "> Target SDK is below 17: every public method of a registered object, including java.lang.Object "
    "methods such as getClass(), is reachable from JavaScript."
)


def signature(method: dict[str, Any]) -> str:
    return f"{method['name']}({', '.join(method['params'])})"


def bridge_title(bridge: dict[str, Any]) -> str:
    static = bridge["static"]
    if bridge["interfaceName"] is not None:
        name = f"`{bridge['interfaceName']}`"
    else:
        source = static["name_source"]
        name = f"`<unresolved: {source['kind']}{' ' + source['ref'] if source.get('ref') else ''}>`"
    if bridge["className"]:
        target = bridge["className"]
    elif static and static["candidate_classes"]:
        target = "one of: " + ", ".join(static["candidate_classes"])
    else:
        target = "unknown class"
    return f"### {name} → {target}  [{bridge['provenance']}]"


def bridge_lines(bridge: dict[str, Any]) -> list[str]:
    static = bridge["static"]
    lines = [bridge_title(bridge), ""]
    if static is None:
        lines.append("- Registered in: not found statically")
        methods = ", ".join(bridge["runtime_methods"]) or "none observed"
        lines.append(f"- Runtime methods: {methods}")
    else:
        lines.append(f"- Registered in: {', '.join(bridge['registered_in'])}")
        lines.append(f"- Class resolution: {static['class_resolution']}")
        lines.append(f"- Exposed methods: {', '.join(signature(m) for m in static['methods']) or 'none'}")
    lines.append(f"- Sensitive methods: {', '.join(bridge['sensitive_methods']) or 'none'}")
    lines.append("")
    return lines


def static_section(section: dict[str, Any]) -> list[str]:
    counts = section["counts"]
    status = section["status"] if section["status"] != "failed" else f"failed — {section['error']}"
    target_sdk = section["target_sdk"] if section["target_sdk"] is not None else "unknown"
    lines = [
        "",
        "## Static Bridge Inventory",
        "",
        f"- Discovery status: {status}",
        f"- Target SDK: {target_sdk}",
        f"- Registrations: {counts['registrations']} ({counts['unresolved_names']} with unresolved names); "
        f"bridge classes: {counts['bridge_classes']}",
        f"- Coverage: {counts['static_and_runtime']} static and runtime, {counts['static_only']} static only, "
        f"{counts['runtime_only']} runtime only",
        "",
    ]
    if section["all_public_methods_exposed"]:
        lines.extend([PRE_17_NOTE, ""])
    for bridge in section["bridges"]:
        lines.extend(bridge_lines(bridge))
    if section["unregistered_classes"]:
        lines.extend(["### Bridge-capable classes with no discovered registration", ""])
        for cls in section["unregistered_classes"]:
            methods = ", ".join(signature(m) + (" [sensitive]" if m["sensitive"] else "") for m in cls["methods"])
            lines.append(f"- {cls['class_name']}: {methods}")
        lines.append("")
    if section["removals"]:
        lines.extend(["### Bridge removals", ""])
        for removal in section["removals"]:
            name = f"`{removal['name']}`" if removal["name"] is not None else "`<unresolved>`"
            call_site = removal["call_site"]
            lines.append(f"- {name} in {call_site['class']}.{call_site['signature']}")
        lines.append("")
    return lines
