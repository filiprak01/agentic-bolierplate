"""File-backed store for Confluence report publication results."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    ConfluenceReportPublicationResult,
    confluence_report_publication_result_to_dict,
)

CONFLUENCE_REPORT_PUBLICATION_FILE = "confluence-report-publication.json"
_SAFE_PUBLICATION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ConfluenceReportPublicationStoreError(RuntimeError):
    """Base error for Confluence publication result storage."""


class InvalidConfluenceReportPublicationKeyError(ConfluenceReportPublicationStoreError):
    """Raised when a publication key is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class ConfluenceReportPublicationLocation:
    publication_issue_key: str
    path: Path


class FileConfluenceReportPublicationStore:
    """Persist Confluence report publication results as JSON."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def result_path(self, publication_issue_key: str) -> Path:
        _validate_key(publication_issue_key)
        return self.root / publication_issue_key / CONFLUENCE_REPORT_PUBLICATION_FILE

    def write(
        self,
        result: ConfluenceReportPublicationResult,
    ) -> ConfluenceReportPublicationLocation:
        path = self.result_path(result.publication_issue_key)
        _atomic_write_json(path, confluence_report_publication_result_to_dict(result))
        return ConfluenceReportPublicationLocation(
            publication_issue_key=result.publication_issue_key,
            path=path,
        )


def _validate_key(publication_issue_key: str) -> None:
    if not _SAFE_PUBLICATION_KEY.fullmatch(publication_issue_key):
        raise InvalidConfluenceReportPublicationKeyError(
            "Confluence publication keys may contain letters, numbers, dots, underscores, and hyphens."
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
