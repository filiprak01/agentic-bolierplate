"""File-backed context pack artifact store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    ContextPack,
    context_pack_from_dict,
    context_pack_to_dict,
    render_context_pack_markdown,
    require_valid_context_pack,
)

CONTEXT_PACK_JSON_FILE = "context-pack.json"
CONTEXT_PACK_MARKDOWN_FILE = "context-pack.md"
_SAFE_CONTEXT_PACK_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ContextPackStoreError(RuntimeError):
    """Base error for context pack store failures."""


class ContextPackNotFoundError(ContextPackStoreError):
    """Raised when a context pack cannot be found."""


class InvalidContextPackKeyError(ContextPackStoreError):
    """Raised when a context pack key is unsafe for deterministic paths."""


@dataclass(frozen=True)
class ContextPackLocation:
    issue_key: str
    directory: Path
    markdown_path: Path
    json_path: Path


class FileContextPackStore:
    """Store context packs as Markdown and JSON under one issue directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def issue_directory(self, issue_key: str) -> Path:
        _validate_issue_key(issue_key)
        return self.root / issue_key

    def markdown_path(self, issue_key: str) -> Path:
        return self.issue_directory(issue_key) / CONTEXT_PACK_MARKDOWN_FILE

    def json_path(self, issue_key: str) -> Path:
        return self.issue_directory(issue_key) / CONTEXT_PACK_JSON_FILE

    def write(self, context_pack: ContextPack) -> ContextPackLocation:
        context_pack = require_valid_context_pack(context_pack)
        directory = self.issue_directory(context_pack.issue_key)
        directory.mkdir(parents=True, exist_ok=True)
        markdown_path = directory / CONTEXT_PACK_MARKDOWN_FILE
        json_path = directory / CONTEXT_PACK_JSON_FILE

        _atomic_write_text(markdown_path, render_context_pack_markdown(context_pack))
        _atomic_write_json(json_path, context_pack_to_dict(context_pack))
        return ContextPackLocation(
            issue_key=context_pack.issue_key,
            directory=directory,
            markdown_path=markdown_path,
            json_path=json_path,
        )

    def read(self, issue_key: str) -> ContextPack:
        path = self.json_path(issue_key)
        if not path.is_file():
            raise ContextPackNotFoundError(f"Context pack {issue_key!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return context_pack_from_dict(json.load(file))


def _validate_issue_key(issue_key: str) -> None:
    if not _SAFE_CONTEXT_PACK_KEY.fullmatch(issue_key):
        raise InvalidContextPackKeyError(
            "Context pack issue keys may contain letters, numbers, dots, underscores, and hyphens."
        )


def _atomic_write_json(path: Path, data: dict) -> None:
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


def _atomic_write_text(path: Path, value: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
