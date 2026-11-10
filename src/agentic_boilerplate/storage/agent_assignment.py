"""File-backed agent registry and assignment store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AgentRegistry,
    WorkerInstance,
    agent_assignment_from_dict,
    agent_assignment_to_dict,
    agent_registry_from_dict,
    agent_registry_to_dict,
    require_valid_agent_assignment,
    require_valid_agent_registry,
    require_valid_worker_instance,
    worker_instance_from_dict,
    worker_instance_to_dict,
)

AGENT_REGISTRY_FILE_SUFFIX = ".json"
AGENT_ASSIGNMENT_FILE_SUFFIX = ".json"
AGENT_WORKER_FILE_SUFFIX = ".json"
AGENT_REGISTRY_FOLDER = "agent-registries"
AGENT_ASSIGNMENT_FOLDER = "agent-assignments"
AGENT_WORKER_FOLDER = "agent-workers"
_SAFE_ASSIGNMENT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class AgentAssignmentStoreError(RuntimeError):
    """Base error for agent assignment store failures."""


class AgentAssignmentNotFoundError(AgentAssignmentStoreError):
    """Raised when an assignment cannot be found."""


class AgentAssignmentAlreadyExistsError(AgentAssignmentStoreError):
    """Raised when creating an assignment would overwrite an existing file."""


class AgentRegistryNotFoundError(AgentAssignmentStoreError):
    """Raised when a registry snapshot cannot be found."""


class AgentRegistryAlreadyExistsError(AgentAssignmentStoreError):
    """Raised when creating a registry would overwrite an existing file."""


class WorkerInstanceNotFoundError(AgentAssignmentStoreError):
    """Raised when a worker instance cannot be found."""


class WorkerInstanceAlreadyExistsError(AgentAssignmentStoreError):
    """Raised when creating a worker would overwrite an existing file."""


class InvalidAgentAssignmentKeyError(AgentAssignmentStoreError):
    """Raised when a key is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class AgentAssignmentLocation:
    id: str
    path: Path


@dataclass(frozen=True)
class AgentRegistryLocation:
    id: str
    path: Path


@dataclass(frozen=True)
class WorkerInstanceLocation:
    id: str
    path: Path


class FileAgentAssignmentStore:
    """Store worker registry and assignment state as durable JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def registry_root(self) -> Path:
        return self.root / AGENT_REGISTRY_FOLDER

    @property
    def assignment_root(self) -> Path:
        return self.root / AGENT_ASSIGNMENT_FOLDER

    @property
    def worker_root(self) -> Path:
        return self.root / AGENT_WORKER_FOLDER

    def ensure_directories(self) -> tuple[Path, Path, Path]:
        directories = (self.registry_root, self.assignment_root, self.worker_root)
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        return directories

    def registry_path(self, registry_id: str) -> Path:
        _validate_key(registry_id)
        return self.registry_root / f"{registry_id}{AGENT_REGISTRY_FILE_SUFFIX}"

    def assignment_path(self, assignment_id: str) -> Path:
        _validate_key(assignment_id)
        return self.assignment_root / f"{assignment_id}{AGENT_ASSIGNMENT_FILE_SUFFIX}"

    def worker_path(self, worker_id: str) -> Path:
        _validate_key(worker_id)
        return self.worker_root / f"{worker_id}{AGENT_WORKER_FILE_SUFFIX}"

    def create_registry(self, registry: AgentRegistry) -> AgentRegistryLocation:
        registry = require_valid_agent_registry(registry)
        self.ensure_directories()
        path = self.registry_path(registry.id)
        if path.exists():
            raise AgentRegistryAlreadyExistsError(f"Agent registry {registry.id!r} already exists.")
        _atomic_write_json(path, agent_registry_to_dict(registry))
        return AgentRegistryLocation(id=registry.id, path=path)

    def save_registry(self, registry: AgentRegistry) -> AgentRegistryLocation:
        registry = require_valid_agent_registry(registry)
        self.ensure_directories()
        path = self.registry_path(registry.id)
        _atomic_write_json(path, agent_registry_to_dict(registry))
        return AgentRegistryLocation(id=registry.id, path=path)

    def read_registry(self, registry_id: str) -> AgentRegistry:
        path = self.registry_path(registry_id)
        if not path.is_file():
            raise AgentRegistryNotFoundError(f"Agent registry {registry_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return agent_registry_from_dict(json.load(file))

    def list_registries(self) -> tuple[AgentRegistry, ...]:
        self.ensure_directories()
        return tuple(
            self.read_registry(path.stem)
            for path in sorted(self.registry_root.glob(f"*{AGENT_REGISTRY_FILE_SUFFIX}"))
        )

    def create_assignment(self, assignment: AgentAssignment) -> AgentAssignmentLocation:
        assignment = require_valid_agent_assignment(assignment)
        self.ensure_directories()
        path = self.assignment_path(assignment.id)
        if path.exists():
            raise AgentAssignmentAlreadyExistsError(f"Agent assignment {assignment.id!r} already exists.")
        _atomic_write_json(path, agent_assignment_to_dict(assignment))
        return AgentAssignmentLocation(id=assignment.id, path=path)

    def save_assignment(self, assignment: AgentAssignment) -> AgentAssignmentLocation:
        assignment = require_valid_agent_assignment(assignment)
        self.ensure_directories()
        path = self.assignment_path(assignment.id)
        _atomic_write_json(path, agent_assignment_to_dict(assignment))
        return AgentAssignmentLocation(id=assignment.id, path=path)

    def read_assignment(self, assignment_id: str) -> AgentAssignment:
        path = self.assignment_path(assignment_id)
        if not path.is_file():
            raise AgentAssignmentNotFoundError(f"Agent assignment {assignment_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return agent_assignment_from_dict(json.load(file))

    def list_assignments(self, *, project_id: str = "") -> tuple[AgentAssignment, ...]:
        self.ensure_directories()
        assignments = tuple(
            self.read_assignment(path.stem)
            for path in sorted(self.assignment_root.glob(f"*{AGENT_ASSIGNMENT_FILE_SUFFIX}"))
        )
        if not project_id:
            return assignments
        return tuple(assignment for assignment in assignments if assignment.project_id == project_id)

    def create_worker(self, worker: WorkerInstance) -> WorkerInstanceLocation:
        worker = require_valid_worker_instance(worker)
        self.ensure_directories()
        path = self.worker_path(worker.id)
        if path.exists():
            raise WorkerInstanceAlreadyExistsError(f"Worker instance {worker.id!r} already exists.")
        _atomic_write_json(path, worker_instance_to_dict(worker))
        return WorkerInstanceLocation(id=worker.id, path=path)

    def save_worker(self, worker: WorkerInstance) -> WorkerInstanceLocation:
        worker = require_valid_worker_instance(worker)
        self.ensure_directories()
        path = self.worker_path(worker.id)
        _atomic_write_json(path, worker_instance_to_dict(worker))
        return WorkerInstanceLocation(id=worker.id, path=path)

    def read_worker(self, worker_id: str) -> WorkerInstance:
        path = self.worker_path(worker_id)
        if not path.is_file():
            raise WorkerInstanceNotFoundError(f"Worker instance {worker_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return worker_instance_from_dict(json.load(file))

    def list_workers(self) -> tuple[WorkerInstance, ...]:
        self.ensure_directories()
        return tuple(
            self.read_worker(path.stem)
            for path in sorted(self.worker_root.glob(f"*{AGENT_WORKER_FILE_SUFFIX}"))
        )


def _validate_key(key: str) -> None:
    if not _SAFE_ASSIGNMENT_KEY.fullmatch(key):
        raise InvalidAgentAssignmentKeyError(
            "Agent assignment store keys may contain letters, numbers, dots, underscores, and hyphens."
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
