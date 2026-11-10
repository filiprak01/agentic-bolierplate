"""File-backed durable agent communication channel store."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessage,
    AgentMessageStatus,
    AgentMessageType,
    agent_message_from_dict,
    agent_message_to_dict,
    mark_agent_message_acknowledged,
    mark_agent_message_consumed,
    redact_agent_message,
    reject_agent_message,
    require_valid_agent_message,
)
from agentic_boilerplate.domain.po_inbox import AgentRole

AGENT_MESSAGE_FILE_SUFFIX = ".json"
AGENT_MESSAGE_FOLDER = "agent-messages"
_SAFE_MESSAGE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class AgentCommunicationStoreError(RuntimeError):
    """Base error for durable agent communication storage failures."""


class AgentMessageAlreadyExistsError(AgentCommunicationStoreError):
    """Raised when a message id already exists with different idempotency."""


class AgentMessageNotFoundError(AgentCommunicationStoreError):
    """Raised when an agent message cannot be found."""


class InvalidAgentMessageKeyError(AgentCommunicationStoreError):
    """Raised when a message id is unsafe for deterministic file paths."""


@dataclass(frozen=True)
class AgentMessageLocation:
    id: str
    path: Path
    created: bool
    duplicate_of: str = ""


class FileAgentCommunicationStore:
    """Store durable agent communication messages as JSON files."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @property
    def message_root(self) -> Path:
        return self.root / AGENT_MESSAGE_FOLDER

    def ensure_directory(self) -> Path:
        self.message_root.mkdir(parents=True, exist_ok=True)
        return self.message_root

    def message_path(self, message_id: str) -> Path:
        _validate_key(message_id)
        return self.message_root / f"{message_id}{AGENT_MESSAGE_FILE_SUFFIX}"

    def publish_message(self, message: AgentMessage) -> AgentMessageLocation:
        """Create a redacted durable message unless its idempotency key already exists."""

        message = redact_agent_message(require_valid_agent_message(message))
        self.ensure_directory()
        duplicate = self.find_by_idempotency_key(message.idempotency_key)
        if duplicate is not None:
            return AgentMessageLocation(
                id=duplicate.id,
                path=self.message_path(duplicate.id),
                created=False,
                duplicate_of=duplicate.id,
            )
        path = self.message_path(message.id)
        if path.exists():
            raise AgentMessageAlreadyExistsError(
                f"Agent message {message.id!r} already exists with a different idempotency key."
            )
        _atomic_write_json(path, agent_message_to_dict(message))
        return AgentMessageLocation(id=message.id, path=path, created=True)

    def save_message(self, message: AgentMessage) -> AgentMessageLocation:
        message = redact_agent_message(require_valid_agent_message(message))
        self.ensure_directory()
        path = self.message_path(message.id)
        created = not path.exists()
        _atomic_write_json(path, agent_message_to_dict(message))
        return AgentMessageLocation(id=message.id, path=path, created=created)

    def read_message(self, message_id: str) -> AgentMessage:
        path = self.message_path(message_id)
        if not path.is_file():
            raise AgentMessageNotFoundError(f"Agent message {message_id!r} was not found.")
        with path.open("r", encoding="utf-8") as file:
            return agent_message_from_dict(json.load(file))

    def list_messages(
        self,
        *,
        status: AgentMessageStatus | None = None,
        project_id: str = "",
        jira_issue_key: str = "",
        assignment_id: str = "",
        target_role: AgentRole | None = None,
        target_channel: AgentCommunicationChannel | None = None,
        message_type: AgentMessageType | None = None,
    ) -> tuple[AgentMessage, ...]:
        """List replayable messages with optional project and routing filters."""

        self.ensure_directory()
        messages = tuple(
            self.read_message(path.stem)
            for path in sorted(self.message_root.glob(f"*{AGENT_MESSAGE_FILE_SUFFIX}"))
        )
        if status is not None:
            messages = tuple(message for message in messages if message.status is status)
        if project_id:
            messages = tuple(message for message in messages if message.project_id == project_id)
        if jira_issue_key:
            normalized_issue = jira_issue_key.strip().upper()
            messages = tuple(message for message in messages if message.jira_issue_key.upper() == normalized_issue)
        if assignment_id:
            messages = tuple(message for message in messages if message.assignment_id == assignment_id)
        if target_role is not None:
            messages = tuple(message for message in messages if message.target_role is target_role)
        if target_channel is not None:
            messages = tuple(message for message in messages if message.target_channel is target_channel)
        if message_type is not None:
            messages = tuple(message for message in messages if message.message_type is message_type)
        return messages

    def find_by_idempotency_key(self, idempotency_key: str) -> AgentMessage | None:
        normalized = idempotency_key.strip()
        if not normalized:
            return None
        for message in self.list_messages():
            if message.idempotency_key == normalized:
                return message
        return None

    def acknowledge_message(self, message_id: str, *, acknowledged_at: str) -> AgentMessage:
        acknowledged = mark_agent_message_acknowledged(
            self.read_message(message_id),
            acknowledged_at=acknowledged_at,
        )
        self.save_message(acknowledged)
        return acknowledged

    def consume_message(self, message_id: str, *, consumed_at: str) -> AgentMessage:
        consumed = mark_agent_message_consumed(self.read_message(message_id), consumed_at=consumed_at)
        self.save_message(consumed)
        return consumed

    def reject_message(self, message_id: str, *, rejected_reason: str, rejected_at: str) -> AgentMessage:
        rejected = reject_agent_message(
            self.read_message(message_id),
            rejected_reason=rejected_reason,
            rejected_at=rejected_at,
        )
        self.save_message(rejected)
        return rejected


def _validate_key(key: str) -> None:
    if not _SAFE_MESSAGE_KEY.fullmatch(key):
        raise InvalidAgentMessageKeyError(
            "Agent message keys may contain letters, numbers, dots, underscores, and hyphens."
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
