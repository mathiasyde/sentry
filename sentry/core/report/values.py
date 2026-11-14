"""core/report: small value helpers shared by tracking, detection and rendering."""

from __future__ import annotations

from typing import Any


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


def compact(value: Any, max_length: int = 240) -> Any:
    if isinstance(value, str) and len(value) > max_length:
        return value[: max_length - 3] + "..."
    if isinstance(value, list):
        return [compact(item, max_length) for item in value[:10]]
    if isinstance(value, dict):
        return {key: compact(val, max_length) for key, val in value.items()}
    return value
