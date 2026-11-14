#!/usr/bin/env python3
"""Compare two raw Sentry event streams after masking run-specific values (FR-004)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

NAMESPACE_RE = re.compile(r"__sentry_webview_[a-z0-9]+")
HASH_KEY_RE = re.compile(r"^([\w.$]+):-?\d+$")
TAINT_ID_RE = re.compile(r"taint-\d+-\d+")
OBJECT_ID_RE = re.compile(r"@[0-9a-f]+\b")


def load(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        start = raw.find("{")
        if not raw or start < 0:
            continue
        try:
            event = json.loads(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "type" in event:
            events.append(event)
    return events


def mask(value: Any, key: str | None = None) -> Any:
    if key in {"timestamp", "retval"}:
        return "<masked>"
    if isinstance(value, dict):
        return {k: mask(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, str):
        value = NAMESPACE_RE.sub("<ns>", value)
        value = TAINT_ID_RE.sub("taint-N", value)
        value = OBJECT_ID_RE.sub("@<id>", value)
        match = HASH_KEY_RE.match(value)
        if match:
            return f"{match.group(1)}:<hash>"
    return value


def shape(event: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    return event.get("type"), tuple(sorted(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    args = parser.parse_args()

    old, new = load(args.old), load(args.new)
    old_shapes, new_shapes = Counter(map(shape, old)), Counter(map(shape, new))
    differences = 0

    for item in sorted(set(old_shapes) | set(new_shapes), key=str):
        if old_shapes[item] != new_shapes[item]:
            differences += 1
            print(f"shape {item[0]} keys={list(item[1])}: old={old_shapes[item]} new={new_shapes[item]}")

    old_payloads = Counter(json.dumps(mask(e), sort_keys=True) for e in old)
    new_payloads = Counter(json.dumps(mask(e), sort_keys=True) for e in new)
    only_old = old_payloads - new_payloads
    only_new = new_payloads - old_payloads
    for payload, count in only_old.items():
        differences += 1
        print(f"- only in old (x{count}): {payload[:300]}")
    for payload, count in only_new.items():
        differences += 1
        print(f"+ only in new (x{count}): {payload[:300]}")

    print(f"{len(old)} old events, {len(new)} new events, {differences} differences")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
