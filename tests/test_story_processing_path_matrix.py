import pytest

from agentic_boilerplate.domain import (
    CANONICAL_STORY_PATH_ROUTES,
    MULTI_PROJECT_PARALLEL_IDENTITY_FIELDS,
    StoryPathEvent,
    StoryPathMessageType,
    StoryPathRole,
    StoryPathStatus,
    StoryPathTransitionRequest,
    decide_story_path_transition,
    get_story_path_route,
    render_story_path_matrix_markdown,
    story_path_routes_for_status,
)


def test_matrix_covers_all_jira_story_statuses() -> None:
    covered_statuses = {route.from_status for route in CANONICAL_STORY_PATH_ROUTES}

    assert covered_statuses == set(StoryPathStatus)


def test_review_merge_confirms_dev_completed_and_requests_tester() -> None:
    route = get_story_path_route("dev-completed.review-merged")

    assert route.from_status == StoryPathStatus.DEV_COMPLETED
    assert route.to_status == StoryPathStatus.DEV_COMPLETED
    assert route.owner_role == StoryPathRole.REVIEW
    assert route.next_role == StoryPathRole.TESTER
    assert route.message_type == StoryPathMessageType.TEST_REQUESTED
    assert "merged_pull_request" in route.required_artifacts
    assert "test_requested_handoff" in route.required_artifacts


def test_tester_owns_in_testing_transition_after_review_handoff() -> None:
    decision = decide_story_path_transition(
        StoryPathTransitionRequest(
            current_status="DEV COMPLETED",
            event=StoryPathEvent.TESTING_STARTED,
            actor=StoryPathRole.TESTER,
            target_status="IN TESTING",
        )
    )

    assert decision.allowed is True
    assert decision.next_status == "IN TESTING"
    assert decision.next_role == StoryPathRole.TESTER
    assert decision.message_type == StoryPathMessageType.TESTING_STARTED
    assert "evidence_path" in decision.required_artifacts


def test_invalid_status_or_actor_is_rejected() -> None:
    wrong_status = decide_story_path_transition(
        StoryPathTransitionRequest(
            current_status="IN PROGRESS",
            event=StoryPathEvent.TESTING_STARTED,
            actor=StoryPathRole.TESTER,
        )
    )
    wrong_actor = decide_story_path_transition(
        StoryPathTransitionRequest(
            current_status="DEV COMPLETED",
            event=StoryPathEvent.TESTING_STARTED,
            actor=StoryPathRole.REVIEW,
        )
    )

    assert wrong_status.allowed is False
    assert "No canonical route" in wrong_status.blockers[0]
    assert wrong_actor.allowed is False
    assert "Transition owner must be tester." in wrong_actor.blockers


def test_failure_pause_resume_regression_and_retro_paths_are_present() -> None:
    required_route_ids = {
        "dev-completed.review-changes-requested",
        "dev-completed.merge-conflict-detected",
        "in-testing.testing-failed",
        "test-completed.regression-failed",
        "in-progress.limit-paused",
        "in-progress.po-question-created",
        "in-progress.po-answer-received",
        "in-progress.worker-crashed",
        "in-progress.stale-assignment-found",
        "test-completed.regression-passed",
        "test-completed.retro-completed",
        "test-completed.closure-completed",
    }

    route_ids = {route.id for route in CANONICAL_STORY_PATH_ROUTES}

    assert required_route_ids <= route_ids


def test_multi_project_identity_fields_are_required_on_every_route() -> None:
    for route in CANONICAL_STORY_PATH_ROUTES:
        assert route.identity_fields == MULTI_PROJECT_PARALLEL_IDENTITY_FIELDS


def test_matrix_renders_ai_consumable_markdown_table() -> None:
    markdown = render_story_path_matrix_markdown()

    assert "| Route | From | Event | Owner | To | Next role | Message | Required artifacts |" in markdown
    assert "dev-completed.review-merged" in markdown
    assert "Review merges and confirms DEV COMPLETED" not in markdown


def test_unknown_route_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_story_path_route("missing-route")


def test_routes_can_be_listed_by_status() -> None:
    routes = story_path_routes_for_status("READY TO START")

    assert {route.id for route in routes} >= {
        "ready.assignment-started",
        "ready.dependency-blocked",
        "ready.context-missing",
        "ready.design-reference-missing",
        "ready.integration-readiness-missing",
    }
