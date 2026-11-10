"""File-backed Product Owner inbox store."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    INBOX_STATUS_FOLDER_NAMES,
    InboxStatus,
    POInboxItem,
    inbox_item_from_dict,
    inbox_item_to_dict,
    require_valid_inbox_item,
)

INBOX_FILE_SUFFIX = ".json"
_SAFE_INBOX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class POInboxStoreError(RuntimeError):
    """Base error for PO inbox store failures."""


class InboxItemNotFoundError(POInboxStoreError):
    """Raised when an inbox item cannot be found by ID."""


class InboxItemAlreadyExistsError(POInboxStoreError):
    """Raised when creating an inbox item would overwrite an existing item."""


class InvalidInboxItemIdError(POInboxStoreError):
    """Raised when an inbox item ID is not safe for deterministic file paths."""


@dataclass(frozen=True)
class InboxItemLocation:
    item_id: str
    status: InboxStatus
    path: Path


class FilePOInboxStore:
    """Store PO inbox items as one JSON file per item under status folders."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def status_directory(self, status: InboxStatus) -> Path:
        return self.root / INBOX_STATUS_FOLDER_NAMES[status]

    def item_path(self, item_id: str, status: InboxStatus) -> Path:
        _validate_item_id(item_id)
        return self.status_directory(status) / f"{item_id}{INBOX_FILE_SUFFIX}"

    def ensure_directories(self) -> tuple[Path, ...]:
        directories = tuple(self.status_directory(status) for status in INBOX_STATUS_FOLDER_NAMES)
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        return directories

    def locate(self, item_id: str) -> InboxItemLocation:
        _validate_item_id(item_id)
        for status in INBOX_STATUS_FOLDER_NAMES:
            path = self.item_path(item_id, status)
            if path.is_file():
                return InboxItemLocation(item_id=item_id, status=status, path=path)
        raise InboxItemNotFoundError(f"PO inbox item {item_id!r} was not found.")

    def create(self, item: POInboxItem) -> InboxItemLocation:
        item = require_valid_inbox_item(item)
        self.ensure_directories()

        try:
            existing = self.locate(item.id)
        except InboxItemNotFoundError:
            existing = None
        if existing is not None:
            raise InboxItemAlreadyExistsError(f"PO inbox item {item.id!r} already exists.")

        path = self.item_path(item.id, item.status)
        _atomic_write_json(path, inbox_item_to_dict(item))
        return InboxItemLocation(item_id=item.id, status=item.status, path=path)

    def read(self, item_id: str) -> POInboxItem:
        location = self.locate(item_id)
        return _read_json_item(location.path)

    def list_items(self, status: InboxStatus | None = None, *, project_id: str = "") -> tuple[POInboxItem, ...]:
        self.ensure_directories()
        statuses = (status,) if status is not None else tuple(INBOX_STATUS_FOLDER_NAMES)
        items: list[POInboxItem] = []
        for current_status in statuses:
            for path in sorted(self.status_directory(current_status).glob(f"*{INBOX_FILE_SUFFIX}")):
                item = _read_json_item(path)
                if project_id and item.project_id != project_id:
                    continue
                items.append(item)
        return tuple(items)

    def update(self, item_id: str, update_fn: Callable[[POInboxItem], POInboxItem]) -> InboxItemLocation:
        current_location = self.locate(item_id)
        current_item = _read_json_item(current_location.path)
        updated_item = require_valid_inbox_item(update_fn(current_item))

        if updated_item.id != item_id:
            raise POInboxStoreError("PO inbox item updates must not change the item ID.")

        self.ensure_directories()
        target_path = self.item_path(updated_item.id, updated_item.status)
        if target_path != current_location.path and target_path.exists():
            raise InboxItemAlreadyExistsError(f"PO inbox item {updated_item.id!r} already exists in target status.")
        _atomic_write_json(target_path, inbox_item_to_dict(updated_item))
        if target_path != current_location.path:
            current_location.path.unlink(missing_ok=True)

        return InboxItemLocation(item_id=updated_item.id, status=updated_item.status, path=target_path)

    def move(self, item_id: str, status: InboxStatus) -> InboxItemLocation:
        return self.update(item_id, lambda item: POInboxItem(**{**item.__dict__, "status": status}))


def _validate_item_id(item_id: str) -> None:
    if not _SAFE_INBOX_ID.fullmatch(item_id):
        raise InvalidInboxItemIdError("Inbox item IDs may contain letters, numbers, dots, underscores, and hyphens.")


def _read_json_item(path: Path) -> POInboxItem:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return inbox_item_from_dict(data)


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
