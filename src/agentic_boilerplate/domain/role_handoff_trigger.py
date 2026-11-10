"""Deterministic role handoff trigger policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessage,
    AgentMessagePriority,
    AgentMessageType,
    agent_message_idempotency_key,
    build_agent_message,
)
from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.story_processing_path_matrix import (
    StoryPathEvent,
    StoryPathMessageType,
    StoryPathRole,
    StoryPathRoute,
    StoryPathTransitionRequest,
    decide_story_path_transition,
)


@dataclass(frozen=True)
class RoleHandoffTriggerInput:
    """Runtime input for converting a story-path event into an agent message."""

    message_id: str
    current_status: str
    event: StoryPathEvent
    actor: StoryPathRole
    project_id: str
    jira_issue_key: str
    assignment_id: str
    workspace_path: str
    context_pack_path: str
    evidence_path: str
    communication_channel_id: str
    created_at: str
    target_status: str = ""
    source_worker_id: str = ""
    project_name: str = ""
    project_root: str = ""
    repository: str = ""
    jira_project_key: str = ""
    sprint_id: str = ""
    sprint_name: str = ""
    branch_name: str = ""
    pull_request_url: str = ""
    merge_sha: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    artifact_values: Mapping[str, str] | None = None
    payload: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RoleHandoffTriggerDecision:
    """Allowed or blocked handoff trigger decision."""

    allowed: bool
    route: StoryPathRoute | None
    message: AgentMessage | None
    blockers: tuple[str, ...] = ()


def build_role_handoff_trigger_message(trigger_input: RoleHandoffTriggerInput) -> RoleHandoffTriggerDecision:
    """Build a durable communication message for an allowed story processing route."""

    transition = decide_story_path_transition(
        StoryPathTransitionRequest(
            current_status=trigger_input.current_status,
            event=trigger_input.event,
            actor=trigger_input.actor,
            target_status=trigger_input.target_status,
        )
    )
    route = transition.route
    blockers: list[str] = list(transition.blockers)
    blockers.extend(_identity_blockers(trigger_input))
    if route is not None:
        blockers.extend(_artifact_blockers(route, trigger_input))
    if blockers:
        return RoleHandoffTriggerDecision(
            allowed=False,
            route=route,
            message=None,
            blockers=tuple(blockers),
        )
    if route is None:
        return RoleHandoffTriggerDecision(
            allowed=False,
            route=None,
            message=None,
            blockers=("No canonical route was selected.",),
        )

    message_type = _agent_message_type_for(route.message_type)
    source_role = _agent_role_for(trigger_input.actor)
    target_role = _target_agent_role_for(route.next_role)
    target_channel = _target_channel_for(route.next_role)
    correlation_id = trigger_input.correlation_id.strip() or trigger_input.communication_channel_id.strip()
    payload = _message_payload(route, trigger_input)
    message = build_agent_message(
        message_id=trigger_input.message_id,
        message_type=message_type,
        idempotency_key=agent_message_idempotency_key(
            message_type=message_type,
            project_id=trigger_input.project_id,
            jira_issue_key=trigger_input.jira_issue_key,
            assignment_id=trigger_input.assignment_id,
            target_role=target_role,
            target_channel=target_channel,
            correlation_id=correlation_id,
            causation_id=trigger_input.causation_id,
        ),
        source_role=source_role,
        target_role=target_role,
        target_channel=target_channel,
        source_worker_id=trigger_input.source_worker_id,
        origin_actor=trigger_input.actor.value,
        created_at=trigger_input.created_at,
        project_id=trigger_input.project_id,
        project_name=trigger_input.project_name,
        project_root=trigger_input.project_root,
        repository=trigger_input.repository,
        jira_project_key=trigger_input.jira_project_key,
        sprint_id=trigger_input.sprint_id,
        sprint_name=trigger_input.sprint_name,
        jira_issue_key=trigger_input.jira_issue_key,
        assignment_id=trigger_input.assignment_id,
        priority=_priority_for(message_type),
        correlation_id=correlation_id,
        causation_id=trigger_input.causation_id,
        payload=payload,
        artifact_refs=_artifact_refs(trigger_input),
        requires_acknowledgement=message_type is not AgentMessageType.STATUS_UPDATE,
    )
    return RoleHandoffTriggerDecision(allowed=True, route=route, message=message)


def build_blocked_role_handoff_message(
    trigger_input: RoleHandoffTriggerInput,
    *,
    blockers: Sequence[str],
    message_id: str,
) -> AgentMessage:
    """Build a durable visible blocker message when a handoff cannot be routed."""

    correlation_id = trigger_input.correlation_id.strip() or trigger_input.communication_channel_id.strip()
    payload = {
        "blocked": True,
        "blockers": tuple(blockers),
        "current_status": trigger_input.current_status,
        "event": trigger_input.event.value,
        "actor": trigger_input.actor.value,
        "target_status": trigger_input.target_status,
        "jira_issue_key": trigger_input.jira_issue_key,
        "assignment_id": trigger_input.assignment_id,
        "communication_channel_id": trigger_input.communication_channel_id,
    }
    return build_agent_message(
        message_id=message_id,
        message_type=AgentMessageType.BLOCKED,
        idempotency_key=agent_message_idempotency_key(
            message_type=AgentMessageType.BLOCKED,
            project_id=trigger_input.project_id,
            jira_issue_key=trigger_input.jira_issue_key,
            assignment_id=trigger_input.assignment_id,
            target_role=AgentRole.SCHEDULER,
            target_channel=AgentCommunicationChannel.ORCHESTRATOR,
            correlation_id=correlation_id,
            causation_id=trigger_input.causation_id or trigger_input.event.value,
        ),
        source_role=_agent_role_for(trigger_input.actor),
        target_role=AgentRole.SCHEDULER,
        target_channel=AgentCommunicationChannel.ORCHESTRATOR,
        source_worker_id=trigger_input.source_worker_id,
        origin_actor=trigger_input.actor.value,
        created_at=trigger_input.created_at,
        project_id=trigger_input.project_id,
        project_name=trigger_input.project_name,
        project_root=trigger_input.project_root,
        repository=trigger_input.repository,
        jira_project_key=trigger_input.jira_project_key,
        sprint_id=trigger_input.sprint_id,
        sprint_name=trigger_input.sprint_name,
        jira_issue_key=trigger_input.jira_issue_key,
        assignment_id=trigger_input.assignment_id,
        priority=AgentMessagePriority.BLOCKING,
        correlation_id=correlation_id,
        causation_id=trigger_input.causation_id,
        payload=payload,
        artifact_refs=_artifact_refs(trigger_input),
        requires_acknowledgement=True,
    )


def _identity_blockers(trigger_input: RoleHandoffTriggerInput) -> tuple[str, ...]:
    required = {
        "message_id": trigger_input.message_id,
        "project_id": trigger_input.project_id,
        "jira_issue_key": trigger_input.jira_issue_key,
        "assignment_id": trigger_input.assignment_id,
        "workspace_path": trigger_input.workspace_path,
        "context_pack_path": trigger_input.context_pack_path,
        "evidence_path": trigger_input.evidence_path,
        "communication_channel_id": trigger_input.communication_channel_id,
        "created_at": trigger_input.created_at,
    }
    return tuple(f"{field} is required for role handoff." for field, value in required.items() if not value.strip())


def _artifact_blockers(route: StoryPathRoute, trigger_input: RoleHandoffTriggerInput) -> tuple[str, ...]:
    return tuple(
        f"Required artifact {artifact!r} is missing for route {route.id}."
        for artifact in route.required_artifacts
        if not _artifact_value(trigger_input, artifact)
    )


def _artifact_value(trigger_input: RoleHandoffTriggerInput, artifact: str) -> str:
    values = dict(trigger_input.artifact_values or {})
    if values.get(artifact, "").strip():
        return values[artifact].strip()
    fallbacks = {
        "pull_request_url": trigger_input.pull_request_url,
        "jira_pr_link": trigger_input.pull_request_url,
        "merged_pull_request": trigger_input.pull_request_url,
        "merge_sha": trigger_input.merge_sha,
        "context_pack": trigger_input.context_pack_path,
        "evidence_path": trigger_input.evidence_path,
        "developer_validation": trigger_input.evidence_path,
        "review_record": trigger_input.evidence_path,
        "test_evidence": trigger_input.evidence_path,
        "regression_evidence": trigger_input.evidence_path,
        "retro_notes": trigger_input.evidence_path,
        "assignment_record": trigger_input.assignment_id,
        "test_requested_handoff": trigger_input.communication_channel_id,
        "completed_subtasks": values.get("completed_subtasks", ""),
        "finding_history": values.get("finding_history", ""),
        "requested_changes": values.get("requested_changes", ""),
        "conflict_report": values.get("conflict_report", ""),
        "linked_bug": values.get("linked_bug", ""),
        "failed_test_evidence": trigger_input.evidence_path,
        "bug_related_labels": values.get("bug_related_labels", ""),
        "retest_scope": values.get("retest_scope", ""),
        "regression_manifest": values.get("regression_manifest", ""),
        "test_execution_links": values.get("test_execution_links", ""),
        "agent_retro_responses": values.get("agent_retro_responses", ""),
        "follow_up_backlog_candidates": values.get("follow_up_backlog_candidates", ""),
        "closure_package": values.get("closure_package", ""),
        "po_batch_acceptance": values.get("po_batch_acceptance", ""),
        "release_notes_or_sprint_summary": values.get("release_notes_or_sprint_summary", ""),
    }
    return str(fallbacks.get(artifact, "")).strip()


def _message_payload(route: StoryPathRoute, trigger_input: RoleHandoffTriggerInput) -> dict[str, Any]:
    artifacts = {artifact: _artifact_value(trigger_input, artifact) for artifact in route.required_artifacts}
    payload = dict(trigger_input.payload or {})
    payload.update(
        {
            "route_id": route.id,
            "story_path_event": route.event.value,
            "story_path_message_type": route.message_type.value,
            "from_status": route.from_status.value,
            "to_status": route.to_status.value,
            "owner_role": route.owner_role.value,
            "next_role": route.next_role.value,
            "required_artifacts": tuple(route.required_artifacts),
            "artifacts": artifacts,
            "workspace_path": trigger_input.workspace_path,
            "context_pack_path": trigger_input.context_pack_path,
            "evidence_path": trigger_input.evidence_path,
            "communication_channel_id": trigger_input.communication_channel_id,
            "branch_name": trigger_input.branch_name,
            "pull_request_url": trigger_input.pull_request_url,
            "merge_sha": trigger_input.merge_sha,
        }
    )
    return payload


def _artifact_refs(trigger_input: RoleHandoffTriggerInput) -> tuple[str, ...]:
    refs = [
        trigger_input.context_pack_path,
        trigger_input.evidence_path,
        *dict(trigger_input.artifact_values or {}).values(),
    ]
    return tuple(dict.fromkeys(ref for ref in refs if ref and ref.strip()))


def _agent_message_type_for(message_type: StoryPathMessageType) -> AgentMessageType:
    mapping = {
        StoryPathMessageType.BACKLOG_READY: AgentMessageType.HANDOFF_REQUEST,
        StoryPathMessageType.ASSIGNMENT_STARTED: AgentMessageType.HANDOFF_REQUEST,
        StoryPathMessageType.ASSIGNMENT_BLOCKED: AgentMessageType.BLOCKED,
        StoryPathMessageType.PR_READY_FOR_REVIEW: AgentMessageType.REVIEW_REQUESTED,
        StoryPathMessageType.REVIEW_REWORK_REQUESTED: AgentMessageType.CHANGES_REQUESTED,
        StoryPathMessageType.TEST_REQUESTED: AgentMessageType.TEST_REQUESTED,
        StoryPathMessageType.TESTING_STARTED: AgentMessageType.STATUS_UPDATE,
        StoryPathMessageType.TESTING_COMPLETED: AgentMessageType.STATUS_UPDATE,
        StoryPathMessageType.BUG_REWORK_REQUESTED: AgentMessageType.BUG_FIX_REQUESTED,
        StoryPathMessageType.REGRESSION_COMPLETED: AgentMessageType.STATUS_UPDATE,
        StoryPathMessageType.REGRESSION_REWORK_REQUESTED: AgentMessageType.BUG_FIX_REQUESTED,
        StoryPathMessageType.RETRO_REQUESTED: AgentMessageType.RETRO_REQUESTED,
        StoryPathMessageType.CLOSURE_READY: AgentMessageType.CLOSURE_READY,
        StoryPathMessageType.LIMIT_PAUSED: AgentMessageType.BLOCKED,
        StoryPathMessageType.PO_QUESTION: AgentMessageType.PO_REQUIRED,
        StoryPathMessageType.PO_RESUME_INSTRUCTION: AgentMessageType.PO_RESUME_INSTRUCTION,
        StoryPathMessageType.OPERATOR_RESCUE_REQUIRED: AgentMessageType.BLOCKED,
        StoryPathMessageType.DEPENDENCY_UNBLOCKED: AgentMessageType.RESUME_REQUEST,
        StoryPathMessageType.RELEASE_ARCHIVED: AgentMessageType.STATUS_UPDATE,
    }
    return mapping[message_type]


def _agent_role_for(role: StoryPathRole) -> AgentRole:
    mapping = {
        StoryPathRole.PRODUCT_OWNER: AgentRole.SCHEDULER,
        StoryPathRole.PRODUCT_PLANNING: AgentRole.PRODUCT_PLANNING,
        StoryPathRole.ARCHITECTURE: AgentRole.ARCHITECTURE,
        StoryPathRole.DEVELOPER: AgentRole.DEVELOPER,
        StoryPathRole.REVIEW: AgentRole.REVIEW,
        StoryPathRole.TESTER: AgentRole.TESTER,
        StoryPathRole.RELEASE_MANAGER: AgentRole.RELEASE_MANAGER,
        StoryPathRole.ORCHESTRATOR: AgentRole.SCHEDULER,
        StoryPathRole.SCHEDULER: AgentRole.SCHEDULER,
        StoryPathRole.OPERATOR: AgentRole.PLATFORM,
    }
    return mapping[role]


def _target_agent_role_for(role: StoryPathRole) -> AgentRole | None:
    if role is StoryPathRole.PRODUCT_OWNER:
        return None
    return _agent_role_for(role)


def _target_channel_for(role: StoryPathRole) -> AgentCommunicationChannel:
    if role is StoryPathRole.PRODUCT_OWNER:
        return AgentCommunicationChannel.PRODUCT_OWNER_OUTBOX
    if role in {StoryPathRole.ORCHESTRATOR, StoryPathRole.SCHEDULER}:
        return AgentCommunicationChannel.ORCHESTRATOR
    return AgentCommunicationChannel.ROLE


def _priority_for(message_type: AgentMessageType) -> AgentMessagePriority:
    if message_type in {
        AgentMessageType.BLOCKED,
        AgentMessageType.PO_REQUIRED,
        AgentMessageType.CHANGES_REQUESTED,
        AgentMessageType.BUG_FIX_REQUESTED,
    }:
        return AgentMessagePriority.BLOCKING
    if message_type in {AgentMessageType.REVIEW_REQUESTED, AgentMessageType.TEST_REQUESTED}:
        return AgentMessagePriority.HIGH
    return AgentMessagePriority.NORMAL
