"""File-backed Jira backlog creation result store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    JiraBacklogCreationResult,
    jira_creation_result_from_dict,
    jira_creation_result_to_dict,
)

JIRA_CREATION_RESULT_FILE_SUFFIX = ".json"
_SAFE_JIRA_CREATION_RESULT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class JiraCreationResultStoreError(RuntimeError):
    """Base error for Jira creation result store failures."""


class JiraCreationResultNotFoundError(JiraCreationResultStoreError):
    """Raised when a creation result cannot be found."""


class InvalidJiraCreationResultKeyError(JiraCreationResultStoreError):
    """Raised when a creation result key is unsafe for deterministic paths."""


@dataclass(frozen=True)
class JiraCreationResultLocation:
    draft_key: str
    path: Path


class FileJiraCreationResultStore:
    """Store Jira creation results as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def ensure_directory(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def result_path(self, draft_key: str) -> Path:
        _validate_result_key(draft_key)
        return self.root / f"{draft_key}{JIRA_CREATION_RESULT_FILE_SUFFIX}"

    def save(self, result: JiraBacklogCreationResult) -> JiraCreationResultLocation:
        self.ensure_directory()
        path = self.result_path(result.draft_key)
        _atomic_write_json(path, jira_creation_result_to_dict(result))
        return JiraCreationResultLocation(draft_key=result.draft_key, path=path)

    def read(self, draft_key: str) -> JiraBacklogCreationResult:
        path = self.result_path(draft_key)
        if not path.is_file():
            raise JiraCreationResultNotFoundError(f"Jira creation result {draft_key!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return jira_creation_result_from_dict(json.load(file))


def _validate_result_key(draft_key: str) -> None:
    if not _SAFE_JIRA_CREATION_RESULT_KEY.fullmatch(draft_key):
        raise InvalidJiraCreationResultKeyError(
            "Jira creation result keys may contain letters, numbers, dots, underscores, and hyphens."
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
