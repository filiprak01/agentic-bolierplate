"""File-backed Test Case coverage mapping store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    TestCaseCoverageMapping,
    coverage_mapping_from_dict,
    coverage_mapping_to_dict,
    require_valid_coverage_mapping,
)

COVERAGE_MAPPING_FILE = "coverage-mapping.json"
_SAFE_TEST_CASE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class CoverageMappingStoreError(RuntimeError):
    """Base error for coverage mapping storage."""


class CoverageMappingNotFoundError(CoverageMappingStoreError):
    """Raised when a coverage mapping cannot be found."""


class InvalidCoverageMappingKeyError(CoverageMappingStoreError):
    """Raised when a Test Case key is unsafe for deterministic paths."""


@dataclass(frozen=True)
class CoverageMappingLocation:
    test_case_key: str
    directory: Path
    path: Path


class FileCoverageMappingStore:
    """Persist Test Case coverage mappings as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def mapping_directory(self, test_case_key: str) -> Path:
        _validate_test_case_key(test_case_key)
        return self.root / test_case_key

    def mapping_path(self, test_case_key: str) -> Path:
        return self.mapping_directory(test_case_key) / COVERAGE_MAPPING_FILE

    def write(self, mapping: TestCaseCoverageMapping) -> CoverageMappingLocation:
        mapping = require_valid_coverage_mapping(mapping)
        directory = self.mapping_directory(mapping.test_case_key)
        path = directory / COVERAGE_MAPPING_FILE
        _atomic_write_json(path, coverage_mapping_to_dict(mapping))
        return CoverageMappingLocation(
            test_case_key=mapping.test_case_key,
            directory=directory,
            path=path,
        )

    def read(self, test_case_key: str) -> TestCaseCoverageMapping:
        path = self.mapping_path(test_case_key)
        if not path.is_file():
            raise CoverageMappingNotFoundError(f"Coverage mapping {test_case_key!r} was not found.")
        return _read_mapping(path)

    def list_mappings(self) -> tuple[TestCaseCoverageMapping, ...]:
        if not self.root.exists():
            return ()
        return tuple(_read_mapping(path) for path in sorted(self.root.glob(f"*/{COVERAGE_MAPPING_FILE}")))


def _validate_test_case_key(test_case_key: str) -> None:
    if not _SAFE_TEST_CASE_KEY.fullmatch(test_case_key):
        raise InvalidCoverageMappingKeyError(
            "Test Case keys may contain letters, numbers, dots, underscores, and hyphens."
        )


def _read_mapping(path: Path) -> TestCaseCoverageMapping:
    with path.open("r", encoding="utf-8") as file:
        return coverage_mapping_from_dict(json.load(file))


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
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
