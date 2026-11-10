"""File-backed backlog draft store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    BacklogDraft,
    backlog_draft_from_dict,
    backlog_draft_to_dict,
)

BACKLOG_DRAFT_FILE_SUFFIX = ".json"
_SAFE_BACKLOG_DRAFT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class BacklogDraftStoreError(RuntimeError):
    """Base error for backlog draft store failures."""


class BacklogDraftNotFoundError(BacklogDraftStoreError):
    """Raised when a backlog draft cannot be found."""


class BacklogDraftAlreadyExistsError(BacklogDraftStoreError):
    """Raised when a backlog draft create would overwrite an existing draft."""


class InvalidBacklogDraftKeyError(BacklogDraftStoreError):
    """Raised when a backlog draft key is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class BacklogDraftLocation:
    key: str
    path: Path


class FileBacklogDraftStore:
    """Store local backlog drafts as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def ensure_directory(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def draft_path(self, key: str) -> Path:
        _validate_draft_key(key)
        return self.root / f"{key}{BACKLOG_DRAFT_FILE_SUFFIX}"

    def create(self, draft: BacklogDraft) -> BacklogDraftLocation:
        self.ensure_directory()
        path = self.draft_path(draft.key)
        if path.exists():
            raise BacklogDraftAlreadyExistsError(f"Backlog draft {draft.key!r} already exists.")
        _atomic_write_json(path, backlog_draft_to_dict(draft))
        return BacklogDraftLocation(key=draft.key, path=path)

    def save(self, draft: BacklogDraft) -> BacklogDraftLocation:
        self.ensure_directory()
        path = self.draft_path(draft.key)
        _atomic_write_json(path, backlog_draft_to_dict(draft))
        return BacklogDraftLocation(key=draft.key, path=path)

    def read(self, key: str) -> BacklogDraft:
        path = self.draft_path(key)
        if not path.is_file():
            raise BacklogDraftNotFoundError(f"Backlog draft {key!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return backlog_draft_from_dict(json.load(file))

    def list_drafts(self) -> tuple[BacklogDraft, ...]:
        self.ensure_directory()
        return tuple(
            self.read(path.stem)
            for path in sorted(self.root.glob(f"*{BACKLOG_DRAFT_FILE_SUFFIX}"))
        )


def _validate_draft_key(key: str) -> None:
    if not _SAFE_BACKLOG_DRAFT_KEY.fullmatch(key):
        raise InvalidBacklogDraftKeyError(
            "Backlog draft keys may contain letters, numbers, dots, underscores, and hyphens."
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
