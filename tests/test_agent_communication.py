import pytest

from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessageSchemaError,
    AgentMessageStatus,
    AgentMessageTransitionError,
    AgentMessageType,
    AgentResumeGateInput,
    agent_message_from_dict,
    agent_message_idempotency_key,
    agent_message_to_dict,
    build_agent_message,
    evaluate_agent_resume_gate,
    mark_agent_message_acknowledged,
    mark_agent_message_consumed,
    redact_agent_message,
)
from agentic_boilerplate.domain.po_inbox import AgentRole


def test_message_type_catalog_includes_handoffs_regression_retro_and_po_messages() -> None:
    values = {message_type.value for message_type in AgentMessageType}

    assert {
        "status_update",
        "handoff_request",
        "review_requested",
        "changes_requested",
        "test_requested",
        "bug_fix_requested",
        "regression_requested",
        "retro_requested",
        "retro_response",
        "closure_ready",
        "po_clarification",
        "po_question_to_agent",
        "po_resume_instruction",
        "agent_response_to_po",
        "scope_change_candidate",
    }.issubset(values)


def test_message_round_trip_preserves_project_scope_artifacts_and_correlation() -> None:
    message = _message(
        message_type=AgentMessageType.REVIEW_REQUESTED,
        target_role=AgentRole.REVIEW,
        target_channel=AgentCommunicationChannel.ROLE,
        payload={"pr_url": "https://github.com/example/repo/pull/1"},
    )

    restored = agent_message_from_dict(agent_message_to_dict(message))

    assert restored == message
    assert restored.project_id == "AP"
    assert restored.jira_issue_key == "AP-29"
    assert restored.correlation_id == "workflow-1"
    assert restored.artifact_refs == ("data/agent-logs/AP-29/evidence.md",)


def test_message_requires_project_identity_and_target() -> None:
    with pytest.raises(AgentMessageSchemaError) as missing_project:
        _message(project_id="")
    with pytest.raises(AgentMessageSchemaError) as missing_target:
        _message(target_role=None, target_channel=None, target_worker_id="")

    assert "message.project_id" in str(missing_project.value)
    assert "message.target" in str(missing_target.value)


def test_message_status_transitions_require_acknowledge_and_consume_timestamps() -> None:
    acknowledged = mark_agent_message_acknowledged(_message(), acknowledged_at="2026-08-10T02:10:00Z")
    consumed = mark_agent_message_consumed(acknowledged, consumed_at="2026-08-10T02:12:00Z")

    assert acknowledged.status is AgentMessageStatus.ACKNOWLEDGED
    assert acknowledged.acknowledged_at == "2026-08-10T02:10:00Z"
    assert consumed.status is AgentMessageStatus.CONSUMED
    assert consumed.consumed_at == "2026-08-10T02:12:00Z"
    with pytest.raises(AgentMessageTransitionError):
        mark_agent_message_acknowledged(consumed, acknowledged_at="2026-08-10T02:13:00Z")


def test_redaction_removes_sensitive_payload_values_and_local_artifact_paths() -> None:
    message = _message(
        project_root="/home/user/business/private-project",
        payload={
            "github_token": "github_" "pat_abcdefghijklmnopqrstuvwxyz1234567890",
            "database_url": "postgresql://user:password@localhost:5432/app",
            "path": "/home/user/business/private-project/.env",
        },
        artifact_refs=("/home/user/business/private-project/evidence.md",),
    )

    redacted = redact_agent_message(message)

    assert redacted.project_root == "[local-path-redacted]"
    assert redacted.payload["github_token"] == "[redacted]"
    assert redacted.payload["database_url"] == "[redacted]"
    assert redacted.payload["path"] == "[local-path-redacted]"
    assert redacted.artifact_refs == ("[local-path-redacted]",)


def test_resume_request_gate_blocks_until_all_orchestration_gates_pass() -> None:
    blocked = evaluate_agent_resume_gate(
        AgentResumeGateInput(
            codex_limit_allows_work=False,
            jira_status_eligible=True,
            dependency_gate_passed=False,
            linked_bugs_clear=True,
            locks_clear=False,
            po_answers_recorded=True,
            required_artifacts_ready=False,
        )
    )
    allowed = evaluate_agent_resume_gate(
        AgentResumeGateInput(
            codex_limit_allows_work=True,
            jira_status_eligible=True,
            dependency_gate_passed=True,
            linked_bugs_clear=True,
            locks_clear=True,
            po_answers_recorded=True,
            required_artifacts_ready=True,
        )
    )

    assert blocked.allowed is False
    assert {
        "codex_limit_gate_closed",
        "dependency_gate_failed",
        "assignment_lock_conflict",
        "required_artifacts_missing",
    }.issubset(set(blocked.blockers))
    assert allowed.allowed is True
    assert allowed.blockers == ()


def test_idempotency_key_includes_project_issue_role_channel_and_causation() -> None:
    key = agent_message_idempotency_key(
        message_type=AgentMessageType.TEST_REQUESTED,
        project_id="ap",
        jira_issue_key="ap-29",
        assignment_id="assignment-1",
        target_role=AgentRole.TESTER,
        target_channel=AgentCommunicationChannel.ROLE,
        correlation_id="workflow-1",
        causation_id="event-1",
    )

    assert key == "test_requested:AP:AP-29:assignment-1:tester:role:workflow-1:event-1"


def _message(
    *,
    message_id: str = "message-1",
    message_type: AgentMessageType = AgentMessageType.HANDOFF_REQUEST,
    project_id: str = "AP",
    target_role: AgentRole | None = AgentRole.REVIEW,
    target_channel: AgentCommunicationChannel | None = AgentCommunicationChannel.ROLE,
    target_worker_id: str = "",
    project_root: str = "",
    payload: dict[str, object] | None = None,
    artifact_refs: tuple[str, ...] = ("data/agent-logs/AP-29/evidence.md",),
):
    return build_agent_message(
        message_id=message_id,
        message_type=message_type,
        idempotency_key=agent_message_idempotency_key(
            message_type=message_type,
            project_id=project_id,
            jira_issue_key="AP-29",
            assignment_id="assignment-1",
            target_role=target_role,
            target_channel=target_channel,
            correlation_id="workflow-1",
        ),
        source_role=AgentRole.DEVELOPER,
        target_role=target_role,
        target_channel=target_channel,
        target_worker_id=target_worker_id,
        created_at="2026-08-10T02:00:00Z",
        project_id=project_id,
        project_name="Airline POC",
        project_root=project_root,
        repository="example-org/airline-poc",
        jira_project_key="AP",
        sprint_id="253",
        jira_issue_key="AP-29",
        assignment_id="assignment-1",
        correlation_id="workflow-1",
        payload=payload or {"summary": "ready for next role"},
        artifact_refs=artifact_refs,
        requires_acknowledgement=True,
    )
