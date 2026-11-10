"""File-backed detached worker checkpoint store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.detached_worker_checkpoint import (
    DetachedWorkerCheckpoint,
    detached_worker_checkpoint_from_dict,
    detached_worker_checkpoint_to_dict,
    redact_detached_worker_checkpoint,
    require_valid_detached_worker_checkpoint,
)

DETACHED_WORKER_CHECKPOINT_FILE_SUFFIX = ".json"
DETACHED_WORKER_CHECKPOINT_FOLDER = "detached-worker-checkpoints"
_SAFE_CHECKPOINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class DetachedWorkerCheckpointStoreError(RuntimeError):
    """Base error for detached worker checkpoint store failures."""


class DetachedWorkerCheckpointAlreadyExistsError(DetachedWorkerCheckpointStoreError):
    """Raised when creating a checkpoint would overwrite an existing file."""


class DetachedWorkerCheckpointNotFoundError(DetachedWorkerCheckpointStoreError):
    """Raised when a checkpoint cannot be found."""


class InvalidDetachedWorkerCheckpointIdError(DetachedWorkerCheckpointStoreError):
    """Raised when a checkpoint id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class DetachedWorkerCheckpointLocation:
    checkpoint_id: str
    path: Path


class FileDetachedWorkerCheckpointStore:
    """Store detached worker checkpoints as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def checkpoint_root(self) -> Path:
        return self.root / DETACHED_WORKER_CHECKPOINT_FOLDER

    def ensure_directories(self) -> tuple[Path, ...]:
        self.checkpoint_root.mkdir(parents=True, exist_ok=True)
        return (self.checkpoint_root,)

    def checkpoint_path(self, checkpoint_id: str) -> Path:
        _validate_checkpoint_id(checkpoint_id)
        return self.checkpoint_root / f"{checkpoint_id}{DETACHED_WORKER_CHECKPOINT_FILE_SUFFIX}"

    def create(self, checkpoint: DetachedWorkerCheckpoint) -> DetachedWorkerCheckpointLocation:
        checkpoint = _safe_checkpoint(checkpoint)
        self.ensure_directories()
        path = self.checkpoint_path(checkpoint.id)
        if path.exists():
            raise DetachedWorkerCheckpointAlreadyExistsError(
                f"Detached worker checkpoint {checkpoint.id!r} already exists."
            )
        _atomic_write_json(path, detached_worker_checkpoint_to_dict(checkpoint))
        return DetachedWorkerCheckpointLocation(checkpoint_id=checkpoint.id, path=path)

    def write(self, checkpoint: DetachedWorkerCheckpoint) -> DetachedWorkerCheckpointLocation:
        checkpoint = _safe_checkpoint(checkpoint)
        self.ensure_directories()
        path = self.checkpoint_path(checkpoint.id)
        _atomic_write_json(path, detached_worker_checkpoint_to_dict(checkpoint))
        return DetachedWorkerCheckpointLocation(checkpoint_id=checkpoint.id, path=path)

    def read(self, checkpoint_id: str) -> DetachedWorkerCheckpoint:
        path = self.checkpoint_path(checkpoint_id)
        if not path.is_file():
            raise DetachedWorkerCheckpointNotFoundError(
                f"Detached worker checkpoint {checkpoint_id!r} was not found."
            )
        with path.open("r", encoding="utf-8") as file:
            return detached_worker_checkpoint_from_dict(json.load(file))

    def list_checkpoints(self) -> tuple[DetachedWorkerCheckpoint, ...]:
        self.ensure_directories()
        return tuple(
            self.read(path.stem)
            for path in sorted(self.checkpoint_root.glob(f"*{DETACHED_WORKER_CHECKPOINT_FILE_SUFFIX}"))
        )

    def list_for_assignment(self, assignment_id: str) -> tuple[DetachedWorkerCheckpoint, ...]:
        return tuple(
            checkpoint
            for checkpoint in self.list_checkpoints()
            if checkpoint.assignment_id == assignment_id
        )


def _safe_checkpoint(checkpoint: DetachedWorkerCheckpoint) -> DetachedWorkerCheckpoint:
    return require_valid_detached_worker_checkpoint(redact_detached_worker_checkpoint(checkpoint))


def _validate_checkpoint_id(checkpoint_id: str) -> None:
    if not _SAFE_CHECKPOINT_ID.fullmatch(checkpoint_id):
        raise InvalidDetachedWorkerCheckpointIdError(
            "Detached worker checkpoint IDs may contain letters, numbers, dots, underscores, and hyphens."
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
