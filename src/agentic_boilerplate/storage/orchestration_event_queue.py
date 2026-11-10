"""File-backed orchestration event queue."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.orchestration_event_queue import (
    OrchestrationEvent,
    OrchestrationEventStatus,
    mark_orchestration_event_processing,
    orchestration_event_from_dict,
    orchestration_event_to_dict,
    require_valid_orchestration_event,
)

ORCHESTRATION_EVENT_FILE_SUFFIX = ".json"
ORCHESTRATION_EVENT_FOLDER = "orchestration-events"
_SAFE_EVENT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class OrchestrationEventQueueStoreError(RuntimeError):
    """Base error for orchestration event queue storage failures."""


class OrchestrationEventAlreadyExistsError(OrchestrationEventQueueStoreError):
    """Raised when an event id already exists with different idempotency."""


class OrchestrationEventNotFoundError(OrchestrationEventQueueStoreError):
    """Raised when an event cannot be found."""


class InvalidOrchestrationEventKeyError(OrchestrationEventQueueStoreError):
    """Raised when an event id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class OrchestrationEventLocation:
    id: str
    path: Path
    created: bool
    duplicate_of: str = ""


class FileOrchestrationEventQueue:
    """Store durable orchestration trigger events as JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def event_root(self) -> Path:
        return self.root / ORCHESTRATION_EVENT_FOLDER

    def ensure_directory(self) -> Path:
        self.event_root.mkdir(parents=True, exist_ok=True)
        return self.event_root

    def event_path(self, event_id: str) -> Path:
        _validate_key(event_id)
        return self.event_root / f"{event_id}{ORCHESTRATION_EVENT_FILE_SUFFIX}"

    def enqueue_event(self, event: OrchestrationEvent) -> OrchestrationEventLocation:
        """Create an event unless its idempotency key already exists."""

        event = require_valid_orchestration_event(event)
        self.ensure_directory()
        duplicate = self.find_by_idempotency_key(event.idempotency_key)
        if duplicate is not None:
            return OrchestrationEventLocation(
                id=duplicate.id,
                path=self.event_path(duplicate.id),
                created=False,
                duplicate_of=duplicate.id,
            )
        path = self.event_path(event.id)
        if path.exists():
            raise OrchestrationEventAlreadyExistsError(
                f"Orchestration event {event.id!r} already exists with a different idempotency key."
            )
        _atomic_write_json(path, orchestration_event_to_dict(event))
        return OrchestrationEventLocation(id=event.id, path=path, created=True)

    def save_event(self, event: OrchestrationEvent) -> OrchestrationEventLocation:
        event = require_valid_orchestration_event(event)
        self.ensure_directory()
        path = self.event_path(event.id)
        created = not path.exists()
        _atomic_write_json(path, orchestration_event_to_dict(event))
        return OrchestrationEventLocation(id=event.id, path=path, created=created)

    def read_event(self, event_id: str) -> OrchestrationEvent:
        path = self.event_path(event_id)
        if not path.is_file():
            raise OrchestrationEventNotFoundError(f"Orchestration event {event_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return orchestration_event_from_dict(json.load(file))

    def list_events(
        self,
        *,
        status: OrchestrationEventStatus | None = None,
        project_id: str = "",
    ) -> tuple[OrchestrationEvent, ...]:
        self.ensure_directory()
        events = tuple(
            self.read_event(path.stem)
            for path in sorted(self.event_root.glob(f"*{ORCHESTRATION_EVENT_FILE_SUFFIX}"))
        )
        if status is not None:
            events = tuple(event for event in events if event.status is status)
        if project_id:
            events = tuple(event for event in events if event.project_id == project_id)
        return events

    def find_by_idempotency_key(self, idempotency_key: str) -> OrchestrationEvent | None:
        normalized = idempotency_key.strip()
        if not normalized:
            return None
        for event in self.list_events():
            if event.idempotency_key == normalized:
                return event
        return None

    def next_queued_event(self) -> OrchestrationEvent | None:
        events = self.list_events(status=OrchestrationEventStatus.QUEUED)
        return events[0] if events else None

    def claim_next_event(self, *, updated_at: str) -> OrchestrationEvent | None:
        event = self.next_queued_event()
        if event is None:
            return None
        claimed = mark_orchestration_event_processing(event, updated_at=updated_at)
        self.save_event(claimed)
        return claimed


def _validate_key(key: str) -> None:
    if not _SAFE_EVENT_KEY.fullmatch(key):
        raise InvalidOrchestrationEventKeyError(
            "Orchestration event keys may contain letters, numbers, dots, underscores, and hyphens."
        )


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
