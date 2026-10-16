"""core/report: read a raw Sentry event log; lines that are not event objects are counted as skipped."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
