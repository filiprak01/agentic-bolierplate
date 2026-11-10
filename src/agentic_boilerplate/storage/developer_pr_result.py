"""File-backed developer pull request result store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import DeveloperPullRequestResult, developer_pull_request_result_to_dict

DEVELOPER_PR_RESULT_FILE = "pull-request.json"
_SAFE_RESULT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class DeveloperPullRequestResultStoreError(RuntimeError):
    """Base error for developer PR result storage."""


class InvalidDeveloperPullRequestResultKeyError(DeveloperPullRequestResultStoreError):
    """Raised when a result key is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class DeveloperPullRequestResultLocation:
    issue_key: str
    path: Path


class FileDeveloperPullRequestResultStore:
    """Persist developer PR creation result metadata as JSON."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def result_path(self, issue_key: str) -> Path:
        _validate_key(issue_key)
        return self.root / issue_key / DEVELOPER_PR_RESULT_FILE

    def write(self, result: DeveloperPullRequestResult) -> DeveloperPullRequestResultLocation:
        path = self.result_path(result.jira_issue_key)
        _atomic_write_json(path, developer_pull_request_result_to_dict(result))
        return DeveloperPullRequestResultLocation(issue_key=result.jira_issue_key, path=path)


def _validate_key(issue_key: str) -> None:
    if not _SAFE_RESULT_KEY.fullmatch(issue_key):
        raise InvalidDeveloperPullRequestResultKeyError(
            "Developer PR result keys may contain letters, numbers, dots, underscores, and hyphens."
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
