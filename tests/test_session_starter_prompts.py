from pathlib import Path


ROLE_FILES = (
    "orchestrator",
    "product_planning",
    "architecture",
    "developer",
    "review",
    "tester",
    "release_manager",
    "frontend",
    "ui_ux",
    "security",
    "docs_confluence",
    "devops_platform",
    "data_persistence",
)


def test_session_starter_prompts_cover_all_roles(project_root: Path) -> None:
    prompts = (project_root / "ai_agents" / "session_starters" / "README.md").read_text(encoding="utf-8")

    for role in ROLE_FILES:
        assert f"ai_agents/roles/{role}.md" in prompts


def test_session_starter_prompts_include_required_operating_context(project_root: Path) -> None:
    prompts = (project_root / "ai_agents" / "session_starters" / "README.md").read_text(encoding="utf-8")

    assert "<PLATFORM_REPO>" in prompts
    assert "<TARGET_PROJECT>" in prompts
    assert "<JIRA_ISSUE>" in prompts
    assert "<SPRINT>" in prompts
    assert "<PLATFORM_REPO>/.agents/skills/codex-quota-guard/SKILL.md" in prompts
    assert "before and after visible stages" in prompts

    for block in _prompt_blocks(prompts):
        assert "Working directory: <PLATFORM_REPO>." in block
        assert "Target project: <TARGET_PROJECT>." in block
        assert "Load AGENTS.md" in block
        assert "PO inbox" in block


def test_session_starter_prompts_stay_short_and_reference_docs(project_root: Path) -> None:
    prompts = (project_root / "ai_agents" / "session_starters" / "README.md").read_text(encoding="utf-8")

    assert "full process manual" in prompts
    assert "## Jira Workflow" not in prompts
    assert "## Git And PR Flow" not in prompts

    for block in _prompt_blocks(prompts):
        lines = [line for line in block.splitlines() if line.strip()]
        assert len(lines) <= 10


def test_agents_md_links_session_starter_prompts(project_root: Path) -> None:
    agents_md = (project_root / "AGENTS.md").read_text(encoding="utf-8")

    assert "ai_agents/session_starters/README.md" in agents_md


def _prompt_blocks(markdown: str) -> tuple[str, ...]:
    blocks: list[str] = []
    in_block = False
    current: list[str] = []
    for line in markdown.splitlines():
        if line.strip() == "```text":
            in_block = True
            current = []
            continue
        if line.strip() == "```" and in_block:
            blocks.append("\n".join(current))
            in_block = False
            continue
        if in_block:
            current.append(line)
    return tuple(blocks)
