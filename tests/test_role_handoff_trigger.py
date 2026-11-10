from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.agent_communication import (
    AgentCommunicationChannel,
    AgentMessagePriority,
    AgentMessageType,
)
from agentic_boilerplate.domain.role_handoff_trigger import (
    RoleHandoffTriggerInput,
    build_blocked_role_handoff_message,
    build_role_handoff_trigger_message,
)
from agentic_boilerplate.domain.story_processing_path_matrix import StoryPathEvent, StoryPathRole


def test_developer_completion_builds_review_requested_handoff() -> None:
    decision = build_role_handoff_trigger_message(
        _trigger_input(
            current_status="IN PROGRESS",
            event=StoryPathEvent.DEVELOPMENT_COMPLETED,
            actor=StoryPathRole.DEVELOPER,
            target_status="DEV COMPLETED",
            pull_request_url="https://github.com/org/repo/pull/42",
            artifact_values={
                "completed_subtasks": "AGENT-805,AGENT-806",
                "developer_validation": "data/agent-logs/AP-29/dev-evidence.md",
                "jira_pr_link": "https://github.com/org/repo/pull/42",
            },
        )
    )

    assert decision.allowed is True
    assert decision.blockers == ()
    assert decision.route is not None
    assert decision.route.id == "in-progress.development-completed"
    assert decision.message is not None
    assert decision.message.message_type is AgentMessageType.REVIEW_REQUESTED
    assert decision.message.source_role is AgentRole.DEVELOPER
    assert decision.message.target_role is AgentRole.REVIEW
    assert decision.message.target_channel is AgentCommunicationChannel.ROLE
    assert decision.message.priority is AgentMessagePriority.HIGH
    assert decision.message.payload["route_id"] == "in-progress.development-completed"
    assert decision.message.payload["artifacts"]["pull_request_url"] == "https://github.com/org/repo/pull/42"
    assert decision.message.payload["context_pack_path"] == "data/context-packs/AP-29/context.md"


def test_review_merge_builds_tester_requested_handoff_without_in_testing_transition() -> None:
    decision = build_role_handoff_trigger_message(
        _trigger_input(
            message_id="handoff-review-merged",
            current_status="DEV COMPLETED",
            event=StoryPathEvent.REVIEW_MERGED,
            actor=StoryPathRole.REVIEW,
            target_status="DEV COMPLETED",
            pull_request_url="https://github.com/org/repo/pull/42",
            merge_sha="abc123",
            artifact_values={
                "review_record": "data/reviews/AP-29/review.md",
                "merged_pull_request": "https://github.com/org/repo/pull/42",
                "merge_sha": "abc123",
                "test_requested_handoff": "channel-ap-29",
            },
        )
    )

    assert decision.allowed is True
    assert decision.route is not None
    assert decision.route.to_status.value == "DEV COMPLETED"
    assert decision.message is not None
    assert decision.message.message_type is AgentMessageType.TEST_REQUESTED
    assert decision.message.source_role is AgentRole.REVIEW
    assert decision.message.target_role is AgentRole.TESTER
    assert decision.message.payload["merge_sha"] == "abc123"
    assert decision.message.payload["next_role"] == "tester"


def test_review_changes_builds_developer_rework_message_with_finding_history() -> None:
    decision = build_role_handoff_trigger_message(
        _trigger_input(
            message_id="handoff-review-rework",
            current_status="DEV COMPLETED",
            event=StoryPathEvent.REVIEW_CHANGES_REQUESTED,
            actor=StoryPathRole.REVIEW,
            artifact_values={
                "review_record": "data/reviews/AP-29/review.md",
                "requested_changes": "fix repeated finding review-001",
                "finding_history": "review-001 seen once",
            },
        )
    )

    assert decision.allowed is True
    assert decision.message is not None
    assert decision.message.message_type is AgentMessageType.CHANGES_REQUESTED
    assert decision.message.target_role is AgentRole.DEVELOPER
    assert decision.message.priority is AgentMessagePriority.BLOCKING
    assert decision.message.payload["artifacts"]["finding_history"] == "review-001 seen once"


def test_tester_pass_notifies_release_manager_that_sprint_readiness_changed() -> None:
    decision = build_role_handoff_trigger_message(
        _trigger_input(
            message_id="handoff-testing-passed",
            current_status="IN TESTING",
            event=StoryPathEvent.TESTING_PASSED,
            actor=StoryPathRole.TESTER,
            target_status="TEST COMPLETED",
            artifact_values={
                "test_evidence": "data/agent-logs/AP-29/test-evidence.md",
                "test_case_or_one_time_validation": "AP-101",
                "coverage_mapping": "data/test-coverage/AP-29.json",
            },
        )
    )

    assert decision.allowed is True
    assert decision.message is not None
    assert decision.message.message_type is AgentMessageType.STATUS_UPDATE
    assert decision.message.target_role is AgentRole.RELEASE_MANAGER
    assert decision.message.payload["story_path_message_type"] == "testing_completed"
    assert decision.message.payload["next_role"] == "release_manager"


def test_missing_required_artifacts_blocks_handoff_before_message_creation() -> None:
    decision = build_role_handoff_trigger_message(
        _trigger_input(
            current_status="IN PROGRESS",
            event=StoryPathEvent.DEVELOPMENT_COMPLETED,
            actor=StoryPathRole.DEVELOPER,
            artifact_values={"completed_subtasks": "AGENT-805"},
        )
    )

    assert decision.allowed is False
    assert decision.message is None
    assert "Required artifact 'pull_request_url' is missing" in "\n".join(decision.blockers)
    assert "Required artifact 'jira_pr_link' is missing" in "\n".join(decision.blockers)


def test_blocked_handoff_message_is_durable_and_targeted_to_orchestrator() -> None:
    blocked = build_blocked_role_handoff_message(
        _trigger_input(
            current_status="IN PROGRESS",
            event=StoryPathEvent.DEVELOPMENT_COMPLETED,
            actor=StoryPathRole.DEVELOPER,
        ),
        blockers=("Required artifact 'pull_request_url' is missing.",),
        message_id="handoff-dev-review-blocked",
    )

    assert blocked.message_type is AgentMessageType.BLOCKED
    assert blocked.priority is AgentMessagePriority.BLOCKING
    assert blocked.target_role is AgentRole.SCHEDULER
    assert blocked.target_channel is AgentCommunicationChannel.ORCHESTRATOR
    assert blocked.payload["blocked"] is True
    assert blocked.payload["blockers"] == ("Required artifact 'pull_request_url' is missing.",)


def _trigger_input(
    *,
    message_id: str = "handoff-dev-review",
    current_status: str,
    event: StoryPathEvent,
    actor: StoryPathRole,
    target_status: str = "",
    pull_request_url: str = "",
    merge_sha: str = "",
    artifact_values: dict[str, str] | None = None,
) -> RoleHandoffTriggerInput:
    return RoleHandoffTriggerInput(
        message_id=message_id,
        current_status=current_status,
        event=event,
        actor=actor,
        target_status=target_status,
        project_id="AP",
        project_name="Airline POC",
        project_root="/workspace/ap",
        repository="example-org/ap",
        jira_project_key="AP",
        sprint_id="ap-s1",
        sprint_name="AP Sprint 1",
        jira_issue_key="AP-29",
        assignment_id="assignment-ap-29",
        workspace_path="/workspaces/AP-29",
        context_pack_path="data/context-packs/AP-29/context.md",
        evidence_path="data/agent-logs/AP-29/evidence.md",
        communication_channel_id="channel-ap-29",
        source_worker_id="developer-1",
        branch_name="feature/AP-29-sample",
        pull_request_url=pull_request_url,
        merge_sha=merge_sha,
        correlation_id="workflow-ap-29",
        causation_id="event-ap-29",
        created_at="2026-08-10T03:00:00Z",
        artifact_values=artifact_values or {},
    )
