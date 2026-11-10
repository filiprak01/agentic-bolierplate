"""File-backed release scope store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain import (
    ReleaseScope,
    SprintScopeSelectionProposal,
    release_scope_from_dict,
    release_scope_to_dict,
    sprint_scope_selection_proposal_from_dict,
    sprint_scope_selection_proposal_to_dict,
)

RELEASE_SCOPE_FILE_SUFFIX = ".json"
SPRINT_SCOPE_PROPOSAL_FILE_SUFFIX = ".json"
RELEASE_SCOPE_FOLDER = "release-scopes"
SPRINT_SCOPE_PROPOSAL_FOLDER = "sprint-scope-proposals"
_SAFE_SCOPE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ReleaseScopeStoreError(RuntimeError):
    """Base error for release scope store failures."""


class ReleaseScopeNotFoundError(ReleaseScopeStoreError):
    """Raised when a release scope cannot be found."""


class ReleaseScopeAlreadyExistsError(ReleaseScopeStoreError):
    """Raised when a release scope create would overwrite an existing file."""


class SprintScopeProposalNotFoundError(ReleaseScopeStoreError):
    """Raised when a sprint scope proposal cannot be found."""


class SprintScopeProposalAlreadyExistsError(ReleaseScopeStoreError):
    """Raised when a sprint scope proposal create would overwrite an existing file."""


class InvalidReleaseScopeKeyError(ReleaseScopeStoreError):
    """Raised when a release scope key is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class ReleaseScopeLocation:
    key: str
    path: Path


@dataclass(frozen=True)
class SprintScopeProposalLocation:
    id: str
    path: Path


class FileReleaseScopeStore:
    """Store release scopes and sprint selection proposals as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def scope_root(self) -> Path:
        return self.root / RELEASE_SCOPE_FOLDER

    @property
    def proposal_root(self) -> Path:
        return self.root / SPRINT_SCOPE_PROPOSAL_FOLDER

    def ensure_directories(self) -> tuple[Path, Path]:
        self.scope_root.mkdir(parents=True, exist_ok=True)
        self.proposal_root.mkdir(parents=True, exist_ok=True)
        return self.scope_root, self.proposal_root

    def scope_path(self, key: str) -> Path:
        _validate_scope_key(key)
        return self.scope_root / f"{key}{RELEASE_SCOPE_FILE_SUFFIX}"

    def proposal_path(self, proposal_id: str) -> Path:
        _validate_scope_key(proposal_id)
        return self.proposal_root / f"{proposal_id}{SPRINT_SCOPE_PROPOSAL_FILE_SUFFIX}"

    def create_scope(self, scope: ReleaseScope) -> ReleaseScopeLocation:
        self.ensure_directories()
        path = self.scope_path(scope.key)
        if path.exists():
            raise ReleaseScopeAlreadyExistsError(f"Release scope {scope.key!r} already exists.")
        _atomic_write_json(path, release_scope_to_dict(scope))
        return ReleaseScopeLocation(key=scope.key, path=path)

    def save_scope(self, scope: ReleaseScope) -> ReleaseScopeLocation:
        self.ensure_directories()
        path = self.scope_path(scope.key)
        _atomic_write_json(path, release_scope_to_dict(scope))
        return ReleaseScopeLocation(key=scope.key, path=path)

    def read_scope(self, key: str) -> ReleaseScope:
        path = self.scope_path(key)
        if not path.is_file():
            raise ReleaseScopeNotFoundError(f"Release scope {key!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return release_scope_from_dict(json.load(file))

    def list_scopes(self) -> tuple[ReleaseScope, ...]:
        self.ensure_directories()
        return tuple(
            self.read_scope(path.stem)
            for path in sorted(self.scope_root.glob(f"*{RELEASE_SCOPE_FILE_SUFFIX}"))
        )

    def create_proposal(
        self,
        proposal: SprintScopeSelectionProposal,
    ) -> SprintScopeProposalLocation:
        self.ensure_directories()
        path = self.proposal_path(proposal.id)
        if path.exists():
            raise SprintScopeProposalAlreadyExistsError(
                f"Sprint scope proposal {proposal.id!r} already exists."
            )
        _atomic_write_json(path, sprint_scope_selection_proposal_to_dict(proposal))
        return SprintScopeProposalLocation(id=proposal.id, path=path)

    def save_proposal(
        self,
        proposal: SprintScopeSelectionProposal,
    ) -> SprintScopeProposalLocation:
        self.ensure_directories()
        path = self.proposal_path(proposal.id)
        _atomic_write_json(path, sprint_scope_selection_proposal_to_dict(proposal))
        return SprintScopeProposalLocation(id=proposal.id, path=path)

    def read_proposal(self, proposal_id: str) -> SprintScopeSelectionProposal:
        path = self.proposal_path(proposal_id)
        if not path.is_file():
            raise SprintScopeProposalNotFoundError(
                f"Sprint scope proposal {proposal_id!r} was not found."
            )
        with path.open("r", encoding="utf-8") as file:
            return sprint_scope_selection_proposal_from_dict(json.load(file))

    def list_proposals(self) -> tuple[SprintScopeSelectionProposal, ...]:
        self.ensure_directories()
        return tuple(
            self.read_proposal(path.stem)
            for path in sorted(
                self.proposal_root.glob(f"*{SPRINT_SCOPE_PROPOSAL_FILE_SUFFIX}")
            )
        )


def _validate_scope_key(key: str) -> None:
    if not _SAFE_SCOPE_KEY.fullmatch(key):
        raise InvalidReleaseScopeKeyError(
            "Release scope keys may contain letters, numbers, dots, underscores, and hyphens."
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
