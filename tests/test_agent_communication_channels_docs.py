from pathlib import Path


def test_agent_communication_channels_doc_defines_scope_types_and_envelope() -> None:
    text = _normalized("docs/agent-communication-channels.md")

    for required in (
        "Status: implemented for `AGENT-674`",
        "project",
        "sprint",
        "jira_issue",
        "role",
        "assignment",
        "orchestrator",
        "product_owner_outbox",
        "Message id and idempotency key",
        "Correlation and causation ids",
        "project_id",
        "artifact references",
        "Duplicate delivery is deduplicated by idempotency key",
        "agentic agent-messages publish-handoff",
    ):
        assert required in text


def test_agent_communication_channels_doc_defines_required_message_loops() -> None:
    text = _normalized("docs/agent-communication-channels.md")

    for required in (
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
        "scope_change_candidate",
        "durable `blocked` message",
    ):
        assert required in text


def test_agent_communication_channels_doc_defines_resume_and_redaction_rules() -> None:
    text = _normalized("docs/agent-communication-channels.md")

    for required in (
        "Codex limit gate allows work",
        "Jira status is eligible",
        "Dependency gate passes",
        "Linked bugs are clear",
        "Assignment locks are clear",
        "Required Product Owner answers are recorded",
        "Required artifacts are available",
        "Raw credentials",
        "database URLs",
        "unsafe local absolute paths",
    ):
        assert required in text


def test_docker_triggering_doc_requires_message_or_no_message_reason() -> None:
    text = _normalized("docs/docker-worker-triggering.md")

    assert "docs/agent-communication-channels.md" in text
    assert "or store an explicit no-message reason" in text
    for required in (
        "Developer completion emits `review_requested`",
        "Review blocked emits `changes_requested`",
        "Review completed emits `test_requested`",
        "Testing failed emits `bug_fix_requested`",
        "Regression readiness emits `regression_requested`",
        "Retro collection emits `retro_requested`",
        "Closure readiness emits `closure_ready`",
    ):
        assert required in text


def _normalized(path: str) -> str:
    return " ".join(Path(path).read_text(encoding="utf-8").split())
