from pathlib import Path

from agentic_boilerplate.domain.worker_instruction_bundle import platform_agents_instruction_path


CORE_ROLE_FILES = {
    "orchestrator": ("gpt-5.5", "high"),
    "architecture": ("gpt-5.5", "extra-high"),
    "product_planning": ("gpt-5.5", "extra-high"),
    "developer": ("gpt-5.4", "high"),
    "review": ("gpt-5.4", "high"),
    "tester": ("gpt-5.4-mini", "high"),
    "release_manager": ("gpt-5.4-mini", "high"),
}

EXPANDED_ROLE_FILES = {
    "frontend": ("gpt-5.4", "high"),
    "ui_ux": ("gpt-5.4", "high"),
    "docs_confluence": ("gpt-5.4-mini", "high"),
    "devops_platform": ("gpt-5.4", "high"),
    "data_persistence": ("gpt-5.4", "high"),
}

MANDATORY_RELEASE_11_ROLES = (
    "frontend",
    "ui_ux",
    "security",
    "docs_confluence",
)


REQUIRED_SECTIONS = (
    "## Purpose",
    "## Default Model And Reasoning",
    "## Inputs",
    "## Outputs",
    "## Stop Conditions",
    "## PO Inbox Behavior",
    "## Workflow References",
)


def test_core_role_instruction_files_cover_required_contract(project_root: Path) -> None:
    roles_dir = project_root / "ai_agents" / "roles"

    for role_name, (model, reasoning) in CORE_ROLE_FILES.items():
        role_path = roles_dir / f"{role_name}.md"
        assert role_path.exists(), f"missing role instruction file: {role_path}"

        content = role_path.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"{role_path} is missing {section}"

        assert "PO inbox" in content
        assert f"Model: `{model}`" in content
        assert f"Reasoning: `{reasoning}`" in content
        assert "docs/" in content


def test_agents_md_links_core_role_instruction_files(project_root: Path) -> None:
    agents_md = platform_agents_instruction_path(project_root).read_text(encoding="utf-8")

    assert "ai_agents/roles/" in agents_md
    for role_name in CORE_ROLE_FILES:
        assert f"ai_agents/roles/{role_name}.md" in agents_md


def test_expanded_role_instruction_files_cover_release_11_contract(project_root: Path) -> None:
    roles_dir = project_root / "ai_agents" / "roles"

    for role_name, (model, reasoning) in EXPANDED_ROLE_FILES.items():
        role_path = roles_dir / f"{role_name}.md"
        assert role_path.exists(), f"missing expanded role instruction file: {role_path}"

        content = role_path.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"{role_path} is missing {section}"

        assert "## Responsibility Boundaries" in content
        assert "PO questions" in content or "PO question" in content
        assert f"Model: `{model}`" in content
        assert f"Reasoning: `{reasoning}`" in content
        assert "docs/" in content

    security = (roles_dir / "security.md").read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in security
    assert "## Responsibility Boundaries" in security
    assert "Model: `gpt-5.5`" in security
    assert "Reasoning: `extra-high`" in security
    assert "Routine scan override: `gpt-5.4` with `high` reasoning" in security


def test_release_11_role_instructions_do_not_default_to_medium(project_root: Path) -> None:
    roles_dir = project_root / "ai_agents" / "roles"
    role_files = tuple(path for path in roles_dir.glob("*.md") if path.name != "README.md")

    assert role_files
    for role_path in role_files:
        content = role_path.read_text(encoding="utf-8")
        assert "Reasoning: `medium`" not in content


def test_expanded_role_instructions_mark_mandatory_and_handoff_rules(project_root: Path) -> None:
    roles_dir = project_root / "ai_agents" / "roles"
    readme = (roles_dir / "README.md").read_text(encoding="utf-8")
    agents_md = platform_agents_instruction_path(project_root).read_text(encoding="utf-8")

    for role_name in MANDATORY_RELEASE_11_ROLES:
        content = (roles_dir / f"{role_name}.md").read_text(encoding="utf-8")
        assert "Mandatory for Release 1.1 validation." in content
        assert role_name + ".md" in readme
        assert f"ai_agents/roles/{role_name}.md" in agents_md

    ui_ux = (roles_dir / "ui_ux.md").read_text(encoding="utf-8")
    assert "## Figma Handoff" in ui_ux
    assert "Figma API or plugin automation is optional" in ui_ux
    assert "access, cost, and workspace permissions" in ui_ux
