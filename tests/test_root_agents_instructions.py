from pathlib import Path


def test_root_agents_md_contains_required_operating_boundaries(project_root: Path) -> None:
    content = (project_root / "AGENTS.md").read_text(encoding="utf-8")

    required_phrases = (
        "Product Owner Control",
        "Jira Workflow",
        "READY TO START",
        "PO Inbox Rule",
        "Session Mode And Docker Boundary",
        "Detached, fully autonomous Docker agents",
        "not Release 1.1 scope",
        "Role-Specific Context",
        "docs/backlog-draft-workflow.md",
        "docs/review-agent-pr-workflow.md",
        "docs/tester-manual-test-workflow.md",
        "agentic setup validate",
    )

    for phrase in required_phrases:
        assert phrase in content


def test_root_agents_md_blocks_direct_main_branch_work(project_root: Path) -> None:
    content = (project_root / "AGENTS.md").read_text(encoding="utf-8")

    assert "Agents must not implement or edit project files directly on `main`" in content
    assert "feature/{JIRA_KEY}-{short-slug}" in content
    assert "Create the pull request after development subtasks are complete" in content
