"""File-backed developer validation evidence writer."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    DeveloperStageValidationResult,
    render_stage_validation_result,
    validation_result_to_dict,
)


class DeveloperValidationStoreError(RuntimeError):
    """Base error for developer validation evidence storage."""


@dataclass(frozen=True)
class DeveloperValidationLocation:
    markdown_path: Path
    json_path: Path


class FileDeveloperValidationStore:
    """Persist developer validation evidence as Markdown and JSON."""

    def write(self, validation: DeveloperStageValidationResult) -> DeveloperValidationLocation:
        if not validation.output_path:
            raise DeveloperValidationStoreError("Validation output_path is required.")
        markdown_path = Path(validation.output_path)
        json_path = markdown_path.with_suffix(".json")
        _atomic_write_text(markdown_path, render_stage_validation_result(validation))
        _atomic_write_text(json_path, json.dumps(validation_result_to_dict(validation), indent=2, sort_keys=True) + "\n")
        return DeveloperValidationLocation(markdown_path=markdown_path, json_path=json_path)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
