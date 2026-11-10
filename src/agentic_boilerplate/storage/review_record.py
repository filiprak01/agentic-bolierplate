"""File-backed review record store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    ReviewRecord,
    require_valid_review_record,
    review_record_from_dict,
    review_record_to_dict,
)

REVIEW_RECORD_FILE = "review-record.json"
_SAFE_REVIEW_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ReviewRecordStoreError(RuntimeError):
    """Base error for review record storage."""


class ReviewRecordAlreadyExistsError(ReviewRecordStoreError):
    """Raised when creating a review record would overwrite an existing record."""


class ReviewRecordNotFoundError(ReviewRecordStoreError):
    """Raised when a review record cannot be found."""


class InvalidReviewRecordIdError(ReviewRecordStoreError):
    """Raised when a review record id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class ReviewRecordLocation:
    review_record_id: str
    path: Path


class FileReviewRecordStore:
    """Persist Review Agent records as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def record_directory(self, review_record_id: str) -> Path:
        _validate_review_record_id(review_record_id)
        return self.root / review_record_id

    def record_path(self, review_record_id: str) -> Path:
        return self.record_directory(review_record_id) / REVIEW_RECORD_FILE

    def create(self, record: ReviewRecord) -> ReviewRecordLocation:
        record = require_valid_review_record(record)
        path = self.record_path(record.id)
        if path.exists():
            raise ReviewRecordAlreadyExistsError(f"Review record {record.id!r} already exists.")
        _atomic_write_json(path, review_record_to_dict(record))
        return ReviewRecordLocation(review_record_id=record.id, path=path)

    def write(self, record: ReviewRecord) -> ReviewRecordLocation:
        record = require_valid_review_record(record)
        path = self.record_path(record.id)
        _atomic_write_json(path, review_record_to_dict(record))
        return ReviewRecordLocation(review_record_id=record.id, path=path)

    def read(self, review_record_id: str) -> ReviewRecord:
        path = self.record_path(review_record_id)
        if not path.is_file():
            raise ReviewRecordNotFoundError(f"Review record {review_record_id!r} was not found.")
        return _read_review_record(path)

    def list_records(self) -> tuple[ReviewRecord, ...]:
        if not self.root.exists():
            return ()
        return tuple(_read_review_record(path) for path in sorted(self.root.glob(f"*/{REVIEW_RECORD_FILE}")))


def _validate_review_record_id(review_record_id: str) -> None:
    if not _SAFE_REVIEW_RECORD_ID.fullmatch(review_record_id):
        raise InvalidReviewRecordIdError(
            "Review record IDs may contain letters, numbers, dots, underscores, and hyphens."
        )


def _read_review_record(path: Path) -> ReviewRecord:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return review_record_from_dict(data)


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
