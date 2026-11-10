"""Canonical story processing path matrix for orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class StoryPathStatus(str, Enum):
    """Jira statuses covered by the canonical story path matrix."""

    FUNNEL = "FUNNEL"
    READY_TO_START = "READY TO START"
    IN_PROGRESS = "IN PROGRESS"
    DEV_COMPLETED = "DEV COMPLETED"
    IN_TESTING = "IN TESTING"
    TEST_COMPLETED = "TEST COMPLETED"
    ACCEPTED_DONE = "ACCEPTED/DONE"


class StoryPathRole(str, Enum):
    """Roles that can own a story path transition."""

    PRODUCT_OWNER = "product_owner"
    PRODUCT_PLANNING = "product_planning"
    ARCHITECTURE = "architecture"
    DEVELOPER = "developer"
    REVIEW = "review"
    TESTER = "tester"
    RELEASE_MANAGER = "release_manager"
    ORCHESTRATOR = "orchestrator"
    SCHEDULER = "scheduler"
    OPERATOR = "operator"


class StoryPathEvent(str, Enum):
    """Durable events that drive story movement or loop routing."""

    PO_SCOPE_APPROVED = "po_scope_approved"
    ASSIGNMENT_STARTED = "assignment_started"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    CONTEXT_MISSING = "context_missing"
    DESIGN_REFERENCE_MISSING = "design_reference_missing"
    INTEGRATION_READINESS_MISSING = "integration_readiness_missing"
    DEVELOPMENT_COMPLETED = "development_completed"
    REVIEW_CHANGES_REQUESTED = "review_changes_requested"
    MERGE_CONFLICT_DETECTED = "merge_conflict_detected"
    REVIEW_MERGED = "review_merged"
    TESTING_STARTED = "testing_started"
    TESTING_PASSED = "testing_passed"
    TESTING_FAILED = "testing_failed"
    REGRESSION_PASSED = "regression_passed"
    REGRESSION_FAILED = "regression_failed"
    RETRO_COMPLETED = "retro_completed"
    CLOSURE_COMPLETED = "closure_completed"
    LIMIT_PAUSED = "limit_paused"
    PO_QUESTION_CREATED = "po_question_created"
    PO_ANSWER_RECEIVED = "po_answer_received"
    WORKER_CRASHED = "worker_crashed"
    STALE_ASSIGNMENT_FOUND = "stale_assignment_found"
    DEPENDENCY_UNBLOCKED = "dependency_unblocked"
    RELEASE_ARCHIVED = "release_archived"


class StoryPathMessageType(str, Enum):
    """Communication message types emitted by the path matrix."""

    BACKLOG_READY = "backlog_ready"
    ASSIGNMENT_STARTED = "assignment_started"
    ASSIGNMENT_BLOCKED = "assignment_blocked"
    PR_READY_FOR_REVIEW = "pr_ready_for_review"
    REVIEW_REWORK_REQUESTED = "review_rework_requested"
    TEST_REQUESTED = "test_requested"
    TESTING_STARTED = "testing_started"
    TESTING_COMPLETED = "testing_completed"
    BUG_REWORK_REQUESTED = "bug_rework_requested"
    REGRESSION_COMPLETED = "regression_completed"
    REGRESSION_REWORK_REQUESTED = "regression_rework_requested"
    RETRO_REQUESTED = "retro_requested"
    CLOSURE_READY = "closure_ready"
    LIMIT_PAUSED = "limit_paused"
    PO_QUESTION = "po_question"
    PO_RESUME_INSTRUCTION = "po_resume_instruction"
    OPERATOR_RESCUE_REQUIRED = "operator_rescue_required"
    DEPENDENCY_UNBLOCKED = "dependency_unblocked"
    RELEASE_ARCHIVED = "release_archived"


MULTI_PROJECT_PARALLEL_IDENTITY_FIELDS = (
    "project_id",
    "jira_issue_key",
    "assignment_id",
    "workspace_path",
    "context_pack_path",
    "evidence_path",
    "communication_channel_id",
)


@dataclass(frozen=True)
class StoryPathRoute:
    """One allowed story-processing route."""

    id: str
    from_status: StoryPathStatus
    event: StoryPathEvent
    owner_role: StoryPathRole
    to_status: StoryPathStatus
    next_role: StoryPathRole
    message_type: StoryPathMessageType
    required_artifacts: tuple[str, ...]
    identity_fields: tuple[str, ...] = MULTI_PROJECT_PARALLEL_IDENTITY_FIELDS
    description: str = ""


@dataclass(frozen=True)
class StoryPathTransitionRequest:
    """Runtime request for validating a story path route."""

    current_status: str
    event: StoryPathEvent
    actor: StoryPathRole
    target_status: str = ""


@dataclass(frozen=True)
class StoryPathTransitionDecision:
    """Allowed or blocked deterministic route decision."""

    allowed: bool
    route: StoryPathRoute | None
    next_status: str
    next_role: StoryPathRole | None
    message_type: StoryPathMessageType | None
    required_artifacts: tuple[str, ...]
    blockers: tuple[str, ...] = ()


CANONICAL_STORY_PATH_ROUTES: tuple[StoryPathRoute, ...] = (
    StoryPathRoute(
        id="funnel.scope-approved",
        from_status=StoryPathStatus.FUNNEL,
        event=StoryPathEvent.PO_SCOPE_APPROVED,
        owner_role=StoryPathRole.PRODUCT_OWNER,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.BACKLOG_READY,
        required_artifacts=("approved_scope", "acceptance_criteria", "dependency_links"),
        description="Product Owner approves backlog scope for execution.",
    ),
    StoryPathRoute(
        id="ready.assignment-started",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.ASSIGNMENT_STARTED,
        owner_role=StoryPathRole.SCHEDULER,
        to_status=StoryPathStatus.IN_PROGRESS,
        next_role=StoryPathRole.DEVELOPER,
        message_type=StoryPathMessageType.ASSIGNMENT_STARTED,
        required_artifacts=("assignment_record", "context_pack", "dependency_gate", "limit_gate", "assignment_lock"),
        description="Scheduler assigns an eligible approved story to Developer.",
    ),
    StoryPathRoute(
        id="ready.dependency-blocked",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.DEPENDENCY_BLOCKED,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.ASSIGNMENT_BLOCKED,
        required_artifacts=("dependency_gate_report", "blocked_issue_keys"),
        description="Story remains ready but cannot be assigned until blockers clear.",
    ),
    StoryPathRoute(
        id="ready.context-missing",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.CONTEXT_MISSING,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.PRODUCT_PLANNING,
        message_type=StoryPathMessageType.ASSIGNMENT_BLOCKED,
        required_artifacts=("missing_context_report", "po_inbox_item_or_followup_story"),
        description="Context gaps stop assignment until docs or PO answers are available.",
    ),
    StoryPathRoute(
        id="ready.design-reference-missing",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.DESIGN_REFERENCE_MISSING,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.PRODUCT_PLANNING,
        message_type=StoryPathMessageType.ASSIGNMENT_BLOCKED,
        required_artifacts=("design_gate_report", "design_story_or_po_override"),
        description="UI implementation waits for an accepted design reference.",
    ),
    StoryPathRoute(
        id="ready.integration-readiness-missing",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.INTEGRATION_READINESS_MISSING,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.OPERATOR,
        message_type=StoryPathMessageType.ASSIGNMENT_BLOCKED,
        required_artifacts=("integration_readiness_report", "setup_diagnostic"),
        description="Missing credentials or provider setup blocks execution.",
    ),
    StoryPathRoute(
        id="in-progress.development-completed",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.DEVELOPMENT_COMPLETED,
        owner_role=StoryPathRole.DEVELOPER,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.REVIEW,
        message_type=StoryPathMessageType.PR_READY_FOR_REVIEW,
        required_artifacts=("completed_subtasks", "developer_validation", "pull_request_url", "jira_pr_link"),
        description="Developer opens a traceable PR and hands off to Review.",
    ),
    StoryPathRoute(
        id="dev-completed.review-changes-requested",
        from_status=StoryPathStatus.DEV_COMPLETED,
        event=StoryPathEvent.REVIEW_CHANGES_REQUESTED,
        owner_role=StoryPathRole.REVIEW,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.DEVELOPER,
        message_type=StoryPathMessageType.REVIEW_REWORK_REQUESTED,
        required_artifacts=("review_record", "requested_changes", "finding_history"),
        description="Review requests Developer rework without creating a product bug.",
    ),
    StoryPathRoute(
        id="dev-completed.merge-conflict-detected",
        from_status=StoryPathStatus.DEV_COMPLETED,
        event=StoryPathEvent.MERGE_CONFLICT_DETECTED,
        owner_role=StoryPathRole.REVIEW,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.DEVELOPER,
        message_type=StoryPathMessageType.REVIEW_REWORK_REQUESTED,
        required_artifacts=("review_record", "conflict_report", "finding_history"),
        description="Review reports merge conflicts to the branch-owning Developer.",
    ),
    StoryPathRoute(
        id="dev-completed.review-merged",
        from_status=StoryPathStatus.DEV_COMPLETED,
        event=StoryPathEvent.REVIEW_MERGED,
        owner_role=StoryPathRole.REVIEW,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.TESTER,
        message_type=StoryPathMessageType.TEST_REQUESTED,
        required_artifacts=("review_record", "merged_pull_request", "merge_sha", "test_requested_handoff"),
        description="Review merges and confirms DEV COMPLETED; Tester owns IN TESTING.",
    ),
    StoryPathRoute(
        id="dev-completed.testing-started",
        from_status=StoryPathStatus.DEV_COMPLETED,
        event=StoryPathEvent.TESTING_STARTED,
        owner_role=StoryPathRole.TESTER,
        to_status=StoryPathStatus.IN_TESTING,
        next_role=StoryPathRole.TESTER,
        message_type=StoryPathMessageType.TESTING_STARTED,
        required_artifacts=("test_plan", "acceptance_criteria", "merged_pull_request", "evidence_path"),
        description="Tester starts validation of merged work.",
    ),
    StoryPathRoute(
        id="in-testing.testing-passed",
        from_status=StoryPathStatus.IN_TESTING,
        event=StoryPathEvent.TESTING_PASSED,
        owner_role=StoryPathRole.TESTER,
        to_status=StoryPathStatus.TEST_COMPLETED,
        next_role=StoryPathRole.RELEASE_MANAGER,
        message_type=StoryPathMessageType.TESTING_COMPLETED,
        required_artifacts=("test_evidence", "test_case_or_one_time_validation", "coverage_mapping"),
        description="Tester passes the story and updates reusable test coverage.",
    ),
    StoryPathRoute(
        id="in-testing.testing-failed",
        from_status=StoryPathStatus.IN_TESTING,
        event=StoryPathEvent.TESTING_FAILED,
        owner_role=StoryPathRole.TESTER,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.DEVELOPER,
        message_type=StoryPathMessageType.BUG_REWORK_REQUESTED,
        required_artifacts=("linked_bug", "failed_test_evidence", "bug_related_labels", "retest_scope"),
        description="Tester creates or links a bug and returns the story for rework.",
    ),
    StoryPathRoute(
        id="test-completed.regression-passed",
        from_status=StoryPathStatus.TEST_COMPLETED,
        event=StoryPathEvent.REGRESSION_PASSED,
        owner_role=StoryPathRole.RELEASE_MANAGER,
        to_status=StoryPathStatus.TEST_COMPLETED,
        next_role=StoryPathRole.RELEASE_MANAGER,
        message_type=StoryPathMessageType.REGRESSION_COMPLETED,
        required_artifacts=("regression_manifest", "regression_evidence", "test_execution_links"),
        description="Release Manager records sprint/release regression pass.",
    ),
    StoryPathRoute(
        id="test-completed.regression-failed",
        from_status=StoryPathStatus.TEST_COMPLETED,
        event=StoryPathEvent.REGRESSION_FAILED,
        owner_role=StoryPathRole.RELEASE_MANAGER,
        to_status=StoryPathStatus.DEV_COMPLETED,
        next_role=StoryPathRole.DEVELOPER,
        message_type=StoryPathMessageType.REGRESSION_REWORK_REQUESTED,
        required_artifacts=("linked_bug", "regression_evidence", "affected_scope", "retest_scope"),
        description="Regression failure creates a linked bug and returns affected work to Developer.",
    ),
    StoryPathRoute(
        id="test-completed.retro-completed",
        from_status=StoryPathStatus.TEST_COMPLETED,
        event=StoryPathEvent.RETRO_COMPLETED,
        owner_role=StoryPathRole.RELEASE_MANAGER,
        to_status=StoryPathStatus.TEST_COMPLETED,
        next_role=StoryPathRole.RELEASE_MANAGER,
        message_type=StoryPathMessageType.RETRO_REQUESTED,
        required_artifacts=("retro_notes", "agent_retro_responses", "follow_up_backlog_candidates"),
        description="Retro feedback is captured before closure without blocking tested stories.",
    ),
    StoryPathRoute(
        id="test-completed.closure-completed",
        from_status=StoryPathStatus.TEST_COMPLETED,
        event=StoryPathEvent.CLOSURE_COMPLETED,
        owner_role=StoryPathRole.RELEASE_MANAGER,
        to_status=StoryPathStatus.ACCEPTED_DONE,
        next_role=StoryPathRole.PRODUCT_OWNER,
        message_type=StoryPathMessageType.CLOSURE_READY,
        required_artifacts=("closure_package", "po_batch_acceptance", "release_notes_or_sprint_summary"),
        description="Release Manager closes tested scope after PO-approved sprint/release gates.",
    ),
    StoryPathRoute(
        id="in-progress.limit-paused",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.LIMIT_PAUSED,
        owner_role=StoryPathRole.SCHEDULER,
        to_status=StoryPathStatus.IN_PROGRESS,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.LIMIT_PAUSED,
        required_artifacts=("paused_assignment", "failed_request", "resume_after", "limit_record"),
        description="Worker pauses safely until limit availability is refreshed.",
    ),
    StoryPathRoute(
        id="in-progress.po-question-created",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.PO_QUESTION_CREATED,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.IN_PROGRESS,
        next_role=StoryPathRole.PRODUCT_OWNER,
        message_type=StoryPathMessageType.PO_QUESTION,
        required_artifacts=("po_inbox_item", "paused_assignment", "decision_context"),
        description="Business/process uncertainty pauses the assignment for Product Owner input.",
    ),
    StoryPathRoute(
        id="in-progress.po-answer-received",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.PO_ANSWER_RECEIVED,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.IN_PROGRESS,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.PO_RESUME_INSTRUCTION,
        required_artifacts=("answered_po_inbox_item", "gate_recheck", "resume_request"),
        description="Orchestrator consumes a PO answer and resumes or reroutes work.",
    ),
    StoryPathRoute(
        id="in-progress.worker-crashed",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.WORKER_CRASHED,
        owner_role=StoryPathRole.SCHEDULER,
        to_status=StoryPathStatus.IN_PROGRESS,
        next_role=StoryPathRole.OPERATOR,
        message_type=StoryPathMessageType.OPERATOR_RESCUE_REQUIRED,
        required_artifacts=("checkpoint", "failed_request", "worker_log", "resume_metadata"),
        description="Crash leaves durable state for operator rescue or safe retry.",
    ),
    StoryPathRoute(
        id="in-progress.stale-assignment-found",
        from_status=StoryPathStatus.IN_PROGRESS,
        event=StoryPathEvent.STALE_ASSIGNMENT_FOUND,
        owner_role=StoryPathRole.OPERATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.OPERATOR_RESCUE_REQUIRED,
        required_artifacts=("stale_lock_report", "operator_rescue_decision", "assignment_release_record"),
        description="Operator releases a stale assignment only after durable safety checks.",
    ),
    StoryPathRoute(
        id="ready.dependency-unblocked",
        from_status=StoryPathStatus.READY_TO_START,
        event=StoryPathEvent.DEPENDENCY_UNBLOCKED,
        owner_role=StoryPathRole.ORCHESTRATOR,
        to_status=StoryPathStatus.READY_TO_START,
        next_role=StoryPathRole.SCHEDULER,
        message_type=StoryPathMessageType.DEPENDENCY_UNBLOCKED,
        required_artifacts=("dependency_gate_report", "eligible_story_scan", "same_sprint_selection"),
        description="A completion event rechecks blocked work and selects the next eligible story.",
    ),
    StoryPathRoute(
        id="accepted-done.release-archived",
        from_status=StoryPathStatus.ACCEPTED_DONE,
        event=StoryPathEvent.RELEASE_ARCHIVED,
        owner_role=StoryPathRole.RELEASE_MANAGER,
        to_status=StoryPathStatus.ACCEPTED_DONE,
        next_role=StoryPathRole.PRODUCT_OWNER,
        message_type=StoryPathMessageType.RELEASE_ARCHIVED,
        required_artifacts=("release_tag", "published_docs", "archive_index"),
        description="Accepted work remains terminal while release artifacts are archived.",
    ),
)


def get_story_path_route(route_id: str) -> StoryPathRoute:
    """Return one canonical route by id."""

    for route in CANONICAL_STORY_PATH_ROUTES:
        if route.id == route_id:
            return route
    raise KeyError(route_id)


def story_path_routes_for_status(status: str | StoryPathStatus) -> tuple[StoryPathRoute, ...]:
    """Return all routes that start from the provided status."""

    normalized = _normalize_status(status)
    return tuple(route for route in CANONICAL_STORY_PATH_ROUTES if route.from_status.value.casefold() == normalized)


def decide_story_path_transition(request: StoryPathTransitionRequest) -> StoryPathTransitionDecision:
    """Validate a requested transition against the canonical path matrix."""

    normalized_status = _normalize_status(request.current_status)
    matching_routes = tuple(
        route
        for route in CANONICAL_STORY_PATH_ROUTES
        if route.from_status.value.casefold() == normalized_status and route.event == request.event
    )
    if not matching_routes:
        return StoryPathTransitionDecision(
            allowed=False,
            route=None,
            next_status=request.target_status.strip(),
            next_role=None,
            message_type=None,
            required_artifacts=(),
            blockers=(f"No canonical route for {request.current_status} on {request.event.value}.",),
        )
    route = matching_routes[0]
    blockers: list[str] = []
    if request.actor != route.owner_role:
        blockers.append(f"Transition owner must be {route.owner_role.value}.")
    requested_target = request.target_status.strip()
    if requested_target and _normalize_status(requested_target) != route.to_status.value.casefold():
        blockers.append(f"Target status must be {route.to_status.value}.")
    return StoryPathTransitionDecision(
        allowed=not blockers,
        route=route,
        next_status=route.to_status.value,
        next_role=route.next_role,
        message_type=route.message_type,
        required_artifacts=route.required_artifacts,
        blockers=tuple(blockers),
    )


def render_story_path_matrix_markdown(routes: Iterable[StoryPathRoute] = CANONICAL_STORY_PATH_ROUTES) -> str:
    """Render the canonical path matrix as Markdown."""

    lines = [
        "# Story Processing Path Matrix",
        "",
        "| Route | From | Event | Owner | To | Next role | Message | Required artifacts |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for route in routes:
        lines.append(
            "| "
            + " | ".join(
                (
                    route.id,
                    route.from_status.value,
                    route.event.value,
                    route.owner_role.value,
                    route.to_status.value,
                    route.next_role.value,
                    route.message_type.value,
                    ", ".join(route.required_artifacts),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _normalize_status(status: str | StoryPathStatus) -> str:
    value = status.value if isinstance(status, StoryPathStatus) else str(status)
    return value.strip().casefold()
