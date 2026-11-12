from pathlib import Path

from agentic_boilerplate.domain.worker_instruction_bundle import platform_agents_instruction_path


def test_root_agents_md_contains_required_operating_boundaries(project_root: Path) -> None:
    content = platform_agents_instruction_path(project_root).read_text(encoding="utf-8")

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
    content = platform_agents_instruction_path(project_root).read_text(encoding="utf-8")

    assert "Agents must not implement or edit project files directly on `main`" in content
    assert "feature/{JIRA_KEY}-{short-slug}" in content
    assert "Create the pull request after development subtasks are complete" in content


def test_public_main_keeps_instructions_without_auto_discovery_entrypoints(project_root: Path) -> None:
    assert not (project_root / "AGENTS.md").exists()
    assert not (project_root / "CLAUDE.md").exists()
    assert platform_agents_instruction_path(project_root) == (
        project_root / "docs/reference/platform-agent-instructions.md"
    )
    assert (project_root / "docs/reference/claude-handoff.md").is_file()
    readme = (project_root / "README.md").read_text(encoding="utf-8")
    assert "release/1.2.0" in readme
    assert "v1.2.0" in readme
    assert "docs/reference/external-tool-mode.md" in readme
