"""File-backed Codex pause and resume artifact store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    CodexFailedRequestArtifact,
    CodexPausedAssignmentArtifact,
    failed_request_artifact_from_dict,
    failed_request_artifact_to_dict,
    paused_assignment_artifact_from_dict,
    paused_assignment_artifact_to_dict,
    redact_failed_request_artifact,
    require_valid_failed_request_artifact,
    require_valid_paused_assignment_artifact,
)

CODEX_PAUSE_FILE_SUFFIX = ".json"
PAUSED_ASSIGNMENTS_FOLDER = "paused-assignments"
FAILED_REQUESTS_FOLDER = "failed-requests"
_SAFE_CODEX_PAUSE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class CodexPauseStoreError(RuntimeError):
    """Base error for Codex pause store failures."""


class CodexPauseArtifactNotFoundError(CodexPauseStoreError):
    """Raised when a Codex pause artifact cannot be found by ID."""


class CodexPauseArtifactAlreadyExistsError(CodexPauseStoreError):
    """Raised when creating a Codex pause artifact would overwrite an existing artifact."""


class InvalidCodexPauseArtifactIdError(CodexPauseStoreError):
    """Raised when a Codex pause artifact ID is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class CodexPauseArtifactLocation:
    artifact_id: str
    kind: str
    path: Path


class FileCodexPauseStore:
    """Store paused assignments and failed requests as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def paused_assignments_directory(self) -> Path:
        return self.root / PAUSED_ASSIGNMENTS_FOLDER

    @property
    def failed_requests_directory(self) -> Path:
        return self.root / FAILED_REQUESTS_FOLDER

    def ensure_directories(self) -> tuple[Path, Path]:
        directories = (self.paused_assignments_directory, self.failed_requests_directory)
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        return directories

    def paused_assignment_path(self, artifact_id: str) -> Path:
        _validate_artifact_id(artifact_id)
        return self.paused_assignments_directory / f"{artifact_id}{CODEX_PAUSE_FILE_SUFFIX}"

    def failed_request_path(self, artifact_id: str) -> Path:
        _validate_artifact_id(artifact_id)
        return self.failed_requests_directory / f"{artifact_id}{CODEX_PAUSE_FILE_SUFFIX}"

    def create_paused_assignment(self, artifact: CodexPausedAssignmentArtifact) -> CodexPauseArtifactLocation:
        artifact = require_valid_paused_assignment_artifact(artifact)
        self.ensure_directories()
        path = self.paused_assignment_path(artifact.id)
        if path.exists():
            raise CodexPauseArtifactAlreadyExistsError(f"Paused assignment {artifact.id!r} already exists.")
        _atomic_write_json(path, paused_assignment_artifact_to_dict(artifact))
        return CodexPauseArtifactLocation(artifact_id=artifact.id, kind="paused_assignment", path=path)

    def read_paused_assignment(self, artifact_id: str) -> CodexPausedAssignmentArtifact:
        path = self.paused_assignment_path(artifact_id)
        if not path.is_file():
            raise CodexPauseArtifactNotFoundError(f"Paused assignment {artifact_id!r} was not found.")
        return _read_paused_assignment(path)

    def list_paused_assignments(self) -> tuple[CodexPausedAssignmentArtifact, ...]:
        self.ensure_directories()
        return tuple(
            _read_paused_assignment(path)
            for path in sorted(self.paused_assignments_directory.glob(f"*{CODEX_PAUSE_FILE_SUFFIX}"))
        )

    def create_failed_request(self, artifact: CodexFailedRequestArtifact) -> CodexPauseArtifactLocation:
        artifact = require_valid_failed_request_artifact(redact_failed_request_artifact(artifact))
        self.ensure_directories()
        path = self.failed_request_path(artifact.id)
        if path.exists():
            raise CodexPauseArtifactAlreadyExistsError(f"Failed request {artifact.id!r} already exists.")
        _atomic_write_json(path, failed_request_artifact_to_dict(artifact))
        return CodexPauseArtifactLocation(artifact_id=artifact.id, kind="failed_request", path=path)

    def read_failed_request(self, artifact_id: str) -> CodexFailedRequestArtifact:
        path = self.failed_request_path(artifact_id)
        if not path.is_file():
            raise CodexPauseArtifactNotFoundError(f"Failed request {artifact_id!r} was not found.")
        return _read_failed_request(path)

    def list_failed_requests(self) -> tuple[CodexFailedRequestArtifact, ...]:
        self.ensure_directories()
        return tuple(
            _read_failed_request(path)
            for path in sorted(self.failed_requests_directory.glob(f"*{CODEX_PAUSE_FILE_SUFFIX}"))
        )


def _validate_artifact_id(artifact_id: str) -> None:
    if not _SAFE_CODEX_PAUSE_ID.fullmatch(artifact_id):
        raise InvalidCodexPauseArtifactIdError(
            "Codex pause artifact IDs may contain letters, numbers, dots, underscores, and hyphens."
        )


def _read_paused_assignment(path: Path) -> CodexPausedAssignmentArtifact:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return paused_assignment_artifact_from_dict(data)


def _read_failed_request(path: Path) -> CodexFailedRequestArtifact:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return failed_request_artifact_from_dict(data)


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
