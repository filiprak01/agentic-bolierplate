from pathlib import Path


TRIGGERING = Path("docs/docker-worker-triggering.md")
READINESS = Path("docs/docker-worker-readiness.md")
SCHEDULER = Path("docs/scheduler-approved-scope-assignment.md")


def test_docker_worker_triggering_doc_exists_with_release_boundary() -> None:
    text = TRIGGERING.read_text()

    assert "Docker Worker Triggering And Handoff Design" in text
    assert "Release 1.1 design baseline" in text
    assert "does not implement live detached Codex execution" in text


def test_docker_worker_triggering_lists_required_events() -> None:
    text = TRIGGERING.read_text()

    for event in (
        "development_completed",
        "review_completed",
        "review_blocked",
        "testing_completed",
        "testing_failed",
        "regression_completed",
        "limit_paused",
        "po_question_created",
    ):
        assert event in text


def test_docker_worker_triggering_defines_handoff_and_fallback_rules() -> None:
    text = TRIGGERING.read_text()

    assert "Developer completion queues Review" in text
    assert "Review completed confirms merge to `main`" in text
    assert "agentic agent-messages publish-handoff" in text
    assert "durable `blocked` message targeted to Orchestrator" in text
    assert "Testing failed creates or links a Bug" in text
    assert "Blocked Story Fallback" in text
    assert "same approved sprint" in text
    assert "build_scheduler_fallback_plan" in text
    assert "render_scheduler_fallback_plan" in text
    assert "same role" in text
    assert "No eligible READY TO START issue" in text


def test_docker_worker_triggering_defines_idempotency_and_guardrails() -> None:
    text = TRIGGERING.read_text()

    assert "Idempotency And Replay" in text
    assert "Duplicate-trigger protection" in text
    assert "Developer completion queues Review" in text
    assert "Duplicate trigger delivery does not create duplicate active assignments" in text


def test_related_docs_link_to_triggering_design() -> None:
    assert "docs/docker-worker-triggering.md" in READINESS.read_text()
    assert "docs/docker-worker-triggering.md" in SCHEDULER.read_text()


def test_scheduler_doc_defines_fallback_skip_categories_and_rendering() -> None:
    text = SCHEDULER.read_text()

    assert "build_scheduler_fallback_plan" in text
    assert "render_scheduler_fallback_plan" in text
    for category in (
        "dependency_blocked",
        "po_blocked",
        "codex_limit_blocked",
        "assignment_locked",
        "conflict_blocked",
        "linked_bug_blocked",
    ):
        assert category in text
