"""Append-only JSONL event storage and read-only replay validation."""

import json
import os
from pathlib import Path

from .contracts import Event, Message, new_id


class EventStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.file = (directory / "events.jsonl").open("x", encoding="utf-8")
        self.run_id = new_id()
        self.sequence = 0
        self.last_event_id = None

    def emit(self, event_type: str, payload: Message | dict) -> Event:
        self.sequence += 1
        event = Event(
            run_id=self.run_id, sequence=self.sequence, event_type=event_type,
            parent_event_ids=[self.last_event_id] if self.last_event_id else [],
            payload=payload.model_dump(mode="json") if isinstance(payload, Message) else payload,
        )
        self.file.write(event.model_dump_json() + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())
        self.last_event_id = event.event_id
        return event

    def close(self):
        self.file.close()


def read_run(path: Path) -> list[Event]:
    events, seen = [], set()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            event = Event.model_validate_json(line)
            if event.event_id in seen or event.sequence != len(events) + 1:
                raise ValueError("Duplicate event or non-contiguous sequence")
            if events and event.run_id != events[0].run_id:
                raise ValueError("Mixed runs")
            if not set(event.parent_event_ids) <= seen:
                raise ValueError("Missing causal parent")
            events.append(event)
            seen.add(event.event_id)
    if not events or events[-1].event_type != "outcome.evaluated":
        raise ValueError("Incomplete run; no terminal outcome")
    return events


def save_json(path: Path, value: dict):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
