from pathlib import Path


def test_orchestration_event_queue_docs_cover_required_events_and_cli() -> None:
    text = Path("docs/orchestration-event-queue.md").read_text()

    for event_type in [
        "assignment_completed",
        "pr_ready",
        "pr_merged",
        "development_completed",
        "test_passed",
        "test_failed",
        "bug_created",
        "regression_requested",
        "regression_completed",
        "retro_requested",
        "retro_response_received",
        "limit_paused",
        "po_blocked",
        "worker_idle",
    ]:
        assert event_type in text

    assert "agentic orchestration-events enqueue" in text
    assert "agentic orchestration-events list --status queued --json" in text
    assert "processed` and `rejected` are terminal" in text


def test_docker_worker_triggering_doc_links_event_queue_contract() -> None:
    text = Path("docs/docker-worker-triggering.md").read_text()

    assert "docs/orchestration-event-queue.md" in text
    assert "regression_requested" in text
    assert "retro_response_received" in text
