from dataclasses import replace
from pathlib import Path

import pytest

from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessageStatus,
    AgentMessageType,
    agent_message_idempotency_key,
    build_agent_message,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.storage.agent_communication import (
    AgentMessageAlreadyExistsError,
    FileAgentCommunicationStore,
)


def test_store_publishes_replayable_messages_after_restart(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    message = _message(message_id="message-1")

    location = store.publish_message(message)
    restored = FileAgentCommunicationStore(tmp_path).read_message("message-1")

    assert location.created is True
    assert restored == message


def test_store_deduplicates_repeated_delivery_by_idempotency_key(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    first = _message(message_id="message-1")
    duplicate = replace(first, id="message-2")

    first_location = store.publish_message(first)
    duplicate_location = store.publish_message(duplicate)

    assert first_location.created is True
    assert duplicate_location.created is False
    assert duplicate_location.duplicate_of == "message-1"
    assert [message.id for message in store.list_messages()] == ["message-1"]


def test_store_rejects_same_id_with_different_idempotency_key(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    store.publish_message(_message(message_id="message-1"))

    with pytest.raises(AgentMessageAlreadyExistsError):
        store.publish_message(_message(message_id="message-1", idempotency_key="different"))


def test_store_lists_messages_by_project_issue_assignment_role_channel_and_type(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    store.publish_message(_message(message_id="ap-review", project_id="AP", target_role=AgentRole.REVIEW))
    store.publish_message(
        _message(
            message_id="other-test",
            project_id="OTHER",
            jira_issue_key="OTHER-1",
            assignment_id="assignment-other",
            target_role=AgentRole.TESTER,
            message_type=AgentMessageType.TEST_REQUESTED,
        )
    )

    assert [message.id for message in store.list_messages(project_id="AP")] == ["ap-review"]
    assert [message.id for message in store.list_messages(jira_issue_key="OTHER-1")] == ["other-test"]
    assert [message.id for message in store.list_messages(assignment_id="assignment-other")] == ["other-test"]
    assert [message.id for message in store.list_messages(target_role=AgentRole.REVIEW)] == ["ap-review"]
    assert [message.id for message in store.list_messages(target_channel=AgentCommunicationChannel.ROLE)] == [
        "ap-review",
        "other-test",
    ]
    assert [message.id for message in store.list_messages(message_type=AgentMessageType.TEST_REQUESTED)] == [
        "other-test"
    ]


def test_store_acknowledges_consumes_and_filters_by_status(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    store.publish_message(_message(message_id="message-1"))

    acknowledged = store.acknowledge_message("message-1", acknowledged_at="2026-08-10T02:10:00Z")
    consumed = store.consume_message("message-1", consumed_at="2026-08-10T02:12:00Z")

    assert acknowledged.status is AgentMessageStatus.ACKNOWLEDGED
    assert consumed.status is AgentMessageStatus.CONSUMED
    assert [message.id for message in store.list_messages(status=AgentMessageStatus.CONSUMED)] == ["message-1"]


def test_store_redacts_sensitive_payload_before_write(tmp_path: Path) -> None:
    store = FileAgentCommunicationStore(tmp_path)
    store.publish_message(
        _message(
            message_id="secret-message",
            project_root="/home/user/business/private-project",
            payload={
                "github_token": "github_" "pat_abcdefghijklmnopqrstuvwxyz1234567890",
                "database_url": "postgresql://user:password@localhost:5432/app",
            },
            artifact_refs=("/home/user/business/private-project/log.md",),
        )
    )

    restored = store.read_message("secret-message")

    assert restored.project_root == "[local-path-redacted]"
    assert restored.payload["github_token"] == "[redacted]"
    assert restored.payload["database_url"] == "[redacted]"
    assert restored.artifact_refs == ("[local-path-redacted]",)


def _message(
    *,
    message_id: str = "message-1",
    idempotency_key: str = "",
    message_type: AgentMessageType = AgentMessageType.REVIEW_REQUESTED,
    project_id: str = "AP",
    jira_issue_key: str = "AP-29",
    assignment_id: str = "assignment-1",
    target_role: AgentRole = AgentRole.REVIEW,
    project_root: str = "",
    payload: dict[str, object] | None = None,
    artifact_refs: tuple[str, ...] = ("data/agent-logs/AP-29/evidence.md",),
):
    return build_agent_message(
        message_id=message_id,
        message_type=message_type,
        idempotency_key=idempotency_key
        or agent_message_idempotency_key(
            message_type=message_type,
            project_id=project_id,
            jira_issue_key=jira_issue_key,
            assignment_id=assignment_id,
            target_role=target_role,
            target_channel=AgentCommunicationChannel.ROLE,
            correlation_id="workflow-1",
        ),
        source_role=AgentRole.DEVELOPER,
        target_role=target_role,
        target_channel=AgentCommunicationChannel.ROLE,
        created_at="2026-08-10T02:00:00Z",
        project_id=project_id,
        project_name=f"{project_id} Project",
        project_root=project_root,
        repository=f"example-org/{project_id.lower()}",
        jira_project_key=project_id,
        sprint_id="253",
        jira_issue_key=jira_issue_key,
        assignment_id=assignment_id,
        correlation_id="workflow-1",
        payload=payload or {"summary": "ready for review"},
        artifact_refs=artifact_refs,
    )
