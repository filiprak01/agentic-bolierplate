from pathlib import Path


def _playbook(project_root: Path) -> str:
    return (project_root / "docs" / "session-mode-planning-handoff-validation.md").read_text(
        encoding="utf-8"
    )


def test_planning_handoff_validation_links_required_workflows(project_root: Path) -> None:
    playbook = _playbook(project_root)

    required_references = (
        "docs/session-mode-validation-playbook.md",
        "ai_agents/session_starters/README.md",
        "ai_agents/roles/architecture.md",
        "ai_agents/roles/product_planning.md",
        "docs/context-pack-generator.md",
        "DURABLE_PO_INBOX_PATH",
    )

    for reference in required_references:
        assert reference in playbook


def test_architecture_session_can_ask_correct_po_inbox_question(project_root: Path) -> None:
    playbook = _playbook(project_root)

    assert "Architecture session passes" in playbook
    assert "PO inbox `blocking_question`" in playbook
    assert "agentic po-inbox create" in playbook
    assert "Stops instead of inventing the missing decision" in playbook


def test_product_planning_creates_reviewable_drafts_without_code(project_root: Path) -> None:
    playbook = _playbook(project_root)

    required_phrases = (
        "Creates a reviewable backlog draft",
        "Keeps the draft local and reviewable before Jira creation",
        "does not require code implementation",
        "without code changes",
        "developer subtasks",
    )

    for phrase in required_phrases:
        assert phrase in playbook


def test_po_approval_gate_precedes_jira_creation(project_root: Path) -> None:
    playbook = _playbook(project_root)

    assert "The approval gate is before Jira story creation." in playbook
    assert "Product Owner approval metadata is recorded with actor and timestamp" in playbook
    assert "Jira creation planning starts only from approved drafts" in playbook
    assert "Jira issues start in `FUNNEL`" in playbook
    assert "Development starts only after the Product Owner moves Jira work to" in playbook


def test_findings_are_recorded_and_feed_future_stories(project_root: Path) -> None:
    playbook = _playbook(project_root)

    required_phrases = (
        "data/agent-logs/<JIRA_ISSUE>/planning-handoff-validation-<timestamp>.md",
        "Any missing behavior that should become a backlog story in `FUNNEL`",
        "docs/docker-worker-requirements.md",
        "docs/docker-worker-triggering.md",
    )

    for phrase in required_phrases:
        assert phrase in playbook
