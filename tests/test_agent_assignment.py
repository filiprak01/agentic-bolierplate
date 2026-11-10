import json
from dataclasses import replace

import pytest

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AgentRegistry,
    AssignmentPaths,
    AssignmentSchemaError,
    AssignmentStackMetadata,
    AssignmentStatus,
    WorkerInstance,
    WorkerStatus,
    agent_assignment_from_dict,
    agent_assignment_to_dict,
    agent_registry_from_dict,
    agent_registry_to_dict,
    assign_worker,
    complete_assignment,
    fail_assignment,
    mark_assignment_in_progress,
    pause_assignment_for_limit,
    pause_assignment_for_po_inbox,
    require_valid_agent_registry,
    resume_assignment_after_po_inbox_answer,
    validate_agent_assignment,
)


def test_agent_assignment_round_trips_to_json_compatible_data() -> None:
    assignment = replace(
        _assignment(),
        project_id="agentic-boilerplate",
        project_name="Agentic Boilerplate",
        project_root="/home/user/business/agentic-bolierplate",
        repository="example-org/agentic-boilerplate",
        jira_project_key="AGENT",
        stack_metadata=AssignmentStackMetadata(
            stack_id="stack-agent-687",
            lane_id="stack-lane-agent-687",
            stack_mode="stacked-dependent",
            resolved_path_version="sprint-r12-s7-20260813T130000Z",
            current_layer=2,
            expected_next_agent="developer",
            stale_state="fresh",
            rebase_required=False,
        ),
    )

    data = agent_assignment_to_dict(assignment)
    restored = agent_assignment_from_dict(data)

    assert data["jira_issue_key"] == "AGENT-40"
    assert data["project_id"] == "agentic-boilerplate"
    assert data["repository"] == "example-org/agentic-boilerplate"
    assert data["role"] == "developer"
    assert data["stack_metadata"]["stack_mode"] == "stacked-dependent"
    assert data["stack_metadata"]["current_layer"] == 2
    assert data["paths"]["context_pack_path"] == "data/context-packs/AGENT-40/context.json"
    assert data["paths"]["workspace_path"] == "data/agent-workspaces/AGENT/AGENT-40/developer"
    assert restored == assignment
    json.dumps(data)


def test_legacy_assignment_records_without_project_identity_still_load() -> None:
    data = agent_assignment_to_dict(_assignment())
    for key in ("project_id", "project_name", "project_root", "repository", "jira_project_key"):
        data.pop(key)
    data.pop("stack_metadata")
    data["paths"].pop("workspace_path")

    restored = agent_assignment_from_dict(data)

    assert restored.project_id == ""
    assert restored.project_name == ""
    assert restored.project_root == ""
    assert restored.repository == ""
    assert restored.jira_project_key == ""
    assert restored.stack_metadata == AssignmentStackMetadata()
    assert restored.paths.workspace_path == ""


def test_assignment_stack_metadata_requires_complete_state_when_present() -> None:
    assignment = replace(
        _assignment(),
        stack_metadata=AssignmentStackMetadata(
            stack_id="stack-agent-687",
            rebase_required=True,
        ),
    )

    issues = validate_agent_assignment(assignment)

    assert {issue.field for issue in issues} == {
        "assignment.stack_metadata.lane_id",
        "assignment.stack_metadata.stack_mode",
        "assignment.stack_metadata.resolved_path_version",
        "assignment.stack_metadata.expected_next_agent",
        "assignment.stack_metadata.current_layer",
        "assignment.stack_metadata.stale_state",
    }


def test_agent_registry_validates_workers_assignments_and_references() -> None:
    worker = _worker()
    assignment = assign_worker(
        _assignment(),
        worker_id=worker.id,
        codex_job_id="codex-job-AGENT-40",
        started_at="2026-06-22T08:00:00Z",
        updated_at="2026-06-22T08:00:00Z",
    )
    registry = AgentRegistry(
        id="registry-main",
        workers=(worker,),
        assignments=(assignment,),
        created_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T08:00:00Z",
    )

    require_valid_agent_registry(registry)
    restored = agent_registry_from_dict(agent_registry_to_dict(registry))

    assert restored == registry


def test_assignment_lifecycle_covers_active_pause_failure_and_completion_states() -> None:
    assigned = assign_worker(
        _assignment(),
        worker_id="developer-1",
        codex_job_id="codex-job-AGENT-40",
        started_at="2026-06-22T08:00:00Z",
        updated_at="2026-06-22T08:00:00Z",
    )
    active = mark_assignment_in_progress(assigned, updated_at="2026-06-22T08:05:00Z")
    paused = pause_assignment_for_limit(
        active,
        failed_request_path="data/codex-jobs/AGENT-40/failed-request.json",
        pause_reason="Codex Plus limit reached.",
        updated_at="2026-06-22T08:30:00Z",
    )
    paused_for_po = pause_assignment_for_po_inbox(
        active,
        worker_id="developer-1",
        po_inbox_item_id="po-blocker-assignment-AGENT-40",
        resume_context_path="data/agent-state/po-inbox-resume-contexts/assignment-AGENT-40.json",
        pause_reason="PO input required: confirm the billing rule.",
        updated_at="2026-06-22T08:35:00Z",
    )
    resumed = resume_assignment_after_po_inbox_answer(
        paused_for_po,
        updated_at="2026-06-22T08:45:00Z",
    )
    failed = fail_assignment(active, failure_reason="Worker container stopped.", updated_at="2026-06-22T08:31:00Z")
    completed = complete_assignment(
        active,
        output_path="data/codex-results/AGENT-40/result.json",
        evidence_path="data/agent-logs/AGENT-40/test-evidence.md",
        completed_at="2026-06-22T09:00:00Z",
    )

    assert active.status is AssignmentStatus.IN_PROGRESS
    assert paused.status is AssignmentStatus.PAUSED_LIMIT
    assert paused.paths.failed_request_path.endswith("failed-request.json")
    assert paused_for_po.status is AssignmentStatus.PAUSED_PO
    assert paused_for_po.po_inbox_item_id == "po-blocker-assignment-AGENT-40"
    assert paused_for_po.paths.po_inbox_resume_context_path.endswith("assignment-AGENT-40.json")
    assert resumed.status is AssignmentStatus.QUEUED
    assert resumed.po_inbox_item_id == "po-blocker-assignment-AGENT-40"
    assert resumed.worker_id == ""
    assert failed.status is AssignmentStatus.FAILED
    assert completed.status is AssignmentStatus.COMPLETED
    assert completed.paths.evidence_path.endswith("test-evidence.md")


def test_paused_assignment_requires_failed_request_path_and_reason() -> None:
    assignment = AgentAssignment(
        **{
            **_assignment().__dict__,
            "status": AssignmentStatus.PAUSED_LIMIT,
            "pause_reason": "",
        }
    )

    issues = validate_agent_assignment(assignment)

    assert {issue.field for issue in issues} == {
        "assignment.codex_job_id",
        "assignment.pause_reason",
        "assignment.paths.failed_request_path",
        "assignment.worker_id",
    }


def test_po_paused_assignment_requires_inbox_reference_and_resume_context() -> None:
    assignment = AgentAssignment(
        **{
            **_assignment().__dict__,
            "status": AssignmentStatus.PAUSED_PO,
            "pause_reason": "",
            "po_inbox_item_id": "",
        }
    )

    issues = validate_agent_assignment(assignment)

    assert {issue.field for issue in issues} == {
        "assignment.pause_reason",
        "assignment.po_inbox_item_id",
        "assignment.paths.po_inbox_resume_context_path",
        "assignment.worker_id",
    }


def test_assigned_assignment_requires_codex_job_id() -> None:
    assignment = AgentAssignment(
        **{
            **_assignment().__dict__,
            "status": AssignmentStatus.ASSIGNED,
            "worker_id": "developer-1",
            "codex_job_id": "",
        }
    )

    issues = validate_agent_assignment(assignment)

    assert {issue.field for issue in issues} == {"assignment.codex_job_id"}


def test_invalid_assignment_transition_is_rejected() -> None:
    completed = complete_assignment(
        assign_worker(
            _assignment(),
            worker_id="developer-1",
            codex_job_id="codex-job-AGENT-40",
            started_at="2026-06-22T08:00:00Z",
            updated_at="2026-06-22T08:00:00Z",
        ),
        completed_at="2026-06-22T09:00:00Z",
    )

    with pytest.raises(AssignmentSchemaError, match="Cannot transition"):
        mark_assignment_in_progress(completed, updated_at="2026-06-22T09:05:00Z")


def _worker() -> WorkerInstance:
    return WorkerInstance(
        id="developer-1",
        role=AgentRole.DEVELOPER,
        status=WorkerStatus.AVAILABLE,
        display_name="Developer 1",
        container_name="agentic-developer-1",
        workspace_path="/workspace/project",
        registered_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T07:55:00Z",
    )


def _assignment() -> AgentAssignment:
    return AgentAssignment(
        id="assignment-AGENT-40",
        jira_issue_key="AGENT-40",
        role=AgentRole.DEVELOPER,
        status=AssignmentStatus.QUEUED,
        paths=AssignmentPaths(
            context_pack_path="data/context-packs/AGENT-40/context.json",
            codex_job_path="data/codex-jobs/AGENT-40/job.json",
            output_path="data/codex-results/AGENT-40/result.json",
            workspace_path="data/agent-workspaces/AGENT/AGENT-40/developer",
        ),
        branch_name="feature/AGENT-40-agent-registry-assignment-store",
        created_at="2026-06-22T07:55:00Z",
        updated_at="2026-06-22T07:55:00Z",
    )
