from dataclasses import replace
from pathlib import Path

import pytest

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.orchestration_event_queue import (
    OrchestrationEventStatus,
    OrchestrationEventTransitionError,
    OrchestrationEventType,
    build_orchestration_event,
    mark_orchestration_event_processed,
    mark_orchestration_event_processing,
    orchestration_event_from_dict,
    orchestration_event_idempotency_key,
    orchestration_event_to_dict,
    reject_orchestration_event,
)
from agentic_boilerplate.storage.orchestration_event_queue import FileOrchestrationEventQueue


def test_event_type_catalog_includes_sprint_end_and_worker_trigger_events() -> None:
    values = {event_type.value for event_type in OrchestrationEventType}

    assert {
        "assignment_completed",
        "pr_ready",
        "pr_merged",
        "development_completed",
        "test_passed",
        "test_failed",
        "bug_created",
        "limit_paused",
        "po_blocked",
        "worker_idle",
        "regression_requested",
        "regression_completed",
        "retro_requested",
        "retro_response_received",
    }.issubset(values)


def test_event_round_trip_preserves_routing_payload_and_idempotency() -> None:
    event = _event(
        event_type=OrchestrationEventType.REGRESSION_REQUESTED,
        target_role=AgentRole.TESTER,
        payload={"sprint_id": "253", "reason": "all stories tested"},
        project_id="AGENT",
    )

    restored = orchestration_event_from_dict(orchestration_event_to_dict(event))

    assert restored == event
    assert restored.idempotency_key == "regression_requested:AGENT-650:assignment-1:r12-s3"
    assert restored.target_role is AgentRole.TESTER
    assert restored.project_id == "AGENT"
    assert restored.payload == {"sprint_id": "253", "reason": "all stories tested"}


def test_legacy_events_without_project_identity_still_load() -> None:
    data = orchestration_event_to_dict(_event())
    for key in ("project_id", "project_name", "project_root", "repository", "jira_project_key"):
        data.pop(key)

    restored = orchestration_event_from_dict(data)

    assert restored.project_id == ""
    assert restored.project_name == ""
    assert restored.project_root == ""
    assert restored.repository == ""
    assert restored.jira_project_key == ""


def test_store_deduplicates_repeated_delivery_by_idempotency_key(tmp_path: Path) -> None:
    store = FileOrchestrationEventQueue(tmp_path)
    first = _event(event_id="event-1")
    duplicate = replace(first, id="event-2")

    first_location = store.enqueue_event(first)
    duplicate_location = store.enqueue_event(duplicate)

    assert first_location.created is True
    assert duplicate_location.created is False
    assert duplicate_location.duplicate_of == "event-1"
    assert store.list_events() == (first,)


def test_store_claims_oldest_queued_event_once(tmp_path: Path) -> None:
    store = FileOrchestrationEventQueue(tmp_path)
    store.enqueue_event(_event(event_id="event-1", idempotency_key="one"))
    store.enqueue_event(_event(event_id="event-2", idempotency_key="two"))

    claimed = store.claim_next_event(updated_at="2026-08-10T02:00:00Z")

    assert claimed is not None
    assert claimed.id == "event-1"
    assert claimed.status is OrchestrationEventStatus.PROCESSING
    assert [event.id for event in store.list_events(status=OrchestrationEventStatus.QUEUED)] == ["event-2"]


def test_store_lists_events_by_project_id(tmp_path: Path) -> None:
    store = FileOrchestrationEventQueue(tmp_path)
    store.enqueue_event(_event(event_id="event-ap", idempotency_key="ap", project_id="AP"))
    store.enqueue_event(_event(event_id="event-agent", idempotency_key="agent", project_id="AGENT"))

    assert [event.id for event in store.list_events(project_id="AP")] == ["event-ap"]
    assert [event.id for event in store.list_events(project_id="AGENT")] == ["event-agent"]


def test_invalid_status_transition_is_rejected() -> None:
    processed = mark_orchestration_event_processed(
        _event(),
        processed_at="2026-08-10T02:05:00Z",
    )

    with pytest.raises(OrchestrationEventTransitionError):
        mark_orchestration_event_processing(processed, updated_at="2026-08-10T02:06:00Z")


def test_rejected_event_requires_visible_reason() -> None:
    rejected = reject_orchestration_event(
        _event(),
        rejected_reason="target role is not eligible for this Jira status",
        updated_at="2026-08-10T02:10:00Z",
    )

    assert rejected.status is OrchestrationEventStatus.REJECTED
    assert rejected.rejected_reason == "target role is not eligible for this Jira status"


def _event(
    *,
    event_id: str = "event-1",
    event_type: OrchestrationEventType = OrchestrationEventType.PR_MERGED,
    idempotency_key: str = "",
    target_role: AgentRole | None = AgentRole.TESTER,
    payload: dict[str, object] | None = None,
    project_id: str = "",
):
    return build_orchestration_event(
        event_id=event_id,
        event_type=event_type,
        idempotency_key=idempotency_key
        or orchestration_event_idempotency_key(
            event_type=event_type,
            jira_issue_key="AGENT-650",
            source_assignment_id="assignment-1",
            scope_key="r12-s3",
        ),
        source_role=AgentRole.REVIEW,
        target_role=target_role,
        created_at="2026-08-10T01:00:00Z",
        jira_issue_key="AGENT-650",
        source_assignment_id="assignment-1",
        scope_key="r12-s3",
        project_id=project_id,
        payload=payload or {},
        evidence_paths=("data/agent-logs/AGENT-650/evidence.md",),
    )
