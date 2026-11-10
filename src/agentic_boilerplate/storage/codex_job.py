"""File-backed Codex job artifact store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    CodexJobArtifact,
    CodexJobStatus,
    codex_job_artifact_from_dict,
    codex_job_artifact_to_dict,
    require_valid_codex_job_artifact,
)

CODEX_JOB_FILE = "job.json"
_SAFE_CODEX_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class CodexJobStoreError(RuntimeError):
    """Base error for Codex job store failures."""


class CodexJobAlreadyExistsError(CodexJobStoreError):
    """Raised when creating a Codex job would overwrite an existing job."""


class CodexJobNotFoundError(CodexJobStoreError):
    """Raised when a Codex job cannot be found."""


class InvalidCodexJobIdError(CodexJobStoreError):
    """Raised when a Codex job id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class CodexJobLocation:
    job_id: str
    path: Path


class FileCodexJobStore:
    """Store Codex job artifacts as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def job_directory(self, job_id: str) -> Path:
        _validate_job_id(job_id)
        return self.root / job_id

    def job_path(self, job_id: str) -> Path:
        return self.job_directory(job_id) / CODEX_JOB_FILE

    def create(self, job: CodexJobArtifact) -> CodexJobLocation:
        job = require_valid_codex_job_artifact(job)
        path = self.job_path(job.id)
        if path.exists():
            raise CodexJobAlreadyExistsError(f"Codex job {job.id!r} already exists.")
        _atomic_write_json(path, codex_job_artifact_to_dict(job))
        return CodexJobLocation(job_id=job.id, path=path)

    def write(self, job: CodexJobArtifact) -> CodexJobLocation:
        job = require_valid_codex_job_artifact(job)
        path = self.job_path(job.id)
        _atomic_write_json(path, codex_job_artifact_to_dict(job))
        return CodexJobLocation(job_id=job.id, path=path)

    def read(self, job_id: str) -> CodexJobArtifact:
        path = self.job_path(job_id)
        if not path.is_file():
            raise CodexJobNotFoundError(f"Codex job {job_id!r} was not found.")
        return _read_job(path)

    def list_jobs(self, *, status: CodexJobStatus | None = None) -> tuple[CodexJobArtifact, ...]:
        if not self.root.exists():
            return ()
        jobs = tuple(_read_job(path) for path in sorted(self.root.glob(f"*/{CODEX_JOB_FILE}")))
        if status is None:
            return jobs
        return tuple(job for job in jobs if job.status == status)

    def list_pending(self) -> tuple[CodexJobArtifact, ...]:
        return self.list_jobs(status=CodexJobStatus.QUEUED)


def _validate_job_id(job_id: str) -> None:
    if not _SAFE_CODEX_JOB_ID.fullmatch(job_id):
        raise InvalidCodexJobIdError("Codex job IDs may contain letters, numbers, dots, underscores, and hyphens.")


def _read_job(path: Path) -> CodexJobArtifact:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return codex_job_artifact_from_dict(data)


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
