"""Minimal Server-Sent Events parser (for async People Set event streams)."""
from __future__ import annotations

import json
from typing import Any, Iterable, Iterator, Optional


class SSEEvent:
    def __init__(self, event: Optional[str], data: str, event_id: Optional[str]) -> None:
        self.event = event
        self.data = data
        self.id = event_id

    def json(self) -> Any:
        return json.loads(self.data)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"SSEEvent(event={self.event!r}, id={self.id!r}, data={self.data[:60]!r})"


def iter_sse(lines: Iterable[str]) -> Iterator[SSEEvent]:
    """Parse an iterable of decoded text lines into SSE events."""
    event, data_lines, event_id = None, [], None
    for line in lines:
        line = line.rstrip("\r\n")
        if line == "":
            if data_lines:
                yield SSEEvent(event, "\n".join(data_lines), event_id)
            event, data_lines, event_id = None, [], None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
        elif field == "id":
            event_id = value
    if data_lines:
        yield SSEEvent(event, "\n".join(data_lines), event_id)
