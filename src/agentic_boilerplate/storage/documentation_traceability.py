"""File-backed documentation traceability report store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.documentation_traceability import (
    DocumentationTraceabilityReport,
    documentation_traceability_report_from_dict,
    documentation_traceability_report_to_dict,
)


DOCUMENTATION_TRACEABILITY_FILE_SUFFIX = ".json"
DOCUMENTATION_TRACEABILITY_FOLDER = "documentation-traceability-reports"
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class DocumentationTraceabilityStoreError(RuntimeError):
    """Base error for documentation traceability report storage."""


class DocumentationTraceabilityReportNotFoundError(DocumentationTraceabilityStoreError):
    """Raised when a report cannot be found."""


class InvalidDocumentationTraceabilityReportIdError(DocumentationTraceabilityStoreError):
    """Raised when a report id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class DocumentationTraceabilityReportLocation:
    report_id: str
    path: Path


class FileDocumentationTraceabilityReportStore:
    """Store documentation traceability reports as durable JSON."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def ensure_directory(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def report_path(self, report_id: str) -> Path:
        _validate_report_id(report_id)
        return self.root / f"{report_id}{DOCUMENTATION_TRACEABILITY_FILE_SUFFIX}"

    def save(self, report: DocumentationTraceabilityReport) -> DocumentationTraceabilityReportLocation:
        self.ensure_directory()
        path = self.report_path(report.id)
        _atomic_write_json(path, documentation_traceability_report_to_dict(report))
        return DocumentationTraceabilityReportLocation(report_id=report.id, path=path)

    def read(self, report_id: str) -> DocumentationTraceabilityReport:
        path = self.report_path(report_id)
        if not path.is_file():
            raise DocumentationTraceabilityReportNotFoundError(f"Documentation traceability report {report_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return documentation_traceability_report_from_dict(json.load(file))

    def list_reports(self) -> tuple[DocumentationTraceabilityReport, ...]:
        self.ensure_directory()
        return tuple(
            self.read(path.stem)
            for path in sorted(self.root.glob(f"*{DOCUMENTATION_TRACEABILITY_FILE_SUFFIX}"))
        )


def _validate_report_id(report_id: str) -> None:
    if not _SAFE_REPORT_ID.fullmatch(report_id):
        raise InvalidDocumentationTraceabilityReportIdError(
            "Documentation traceability report ids may contain letters, numbers, dots, underscores, and hyphens."
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
