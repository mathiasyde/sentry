"""core/events: the single event vocabulary shared by the agent and the report pipeline."""

from __future__ import annotations

import json
from pathlib import Path

EVENT_TYPES: dict[str, str] = json.loads(
    Path(__file__).with_name("event_types.json").read_text(encoding="utf-8")
)

ALL: tuple[str, ...] = tuple(EVENT_TYPES.values())


class EventType:
    """Event type wire strings, e.g. ``EventType.URL_LOADED == "url.loaded"``."""


for _name, _value in EVENT_TYPES.items():
    setattr(EventType, _name, _value)
