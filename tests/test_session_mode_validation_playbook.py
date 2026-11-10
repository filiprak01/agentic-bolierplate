from pathlib import Path


ROLE_SECTIONS = (
    ("Orchestrator", "ai_agents/roles/orchestrator.md"),
    ("Product Planning", "ai_agents/roles/product_planning.md"),
    ("Architecture", "ai_agents/roles/architecture.md"),
    ("Developer", "ai_agents/roles/developer.md"),
    ("Review", "ai_agents/roles/review.md"),
    ("Tester", "ai_agents/roles/tester.md"),
    ("Release Manager", "ai_agents/roles/release_manager.md"),
    ("Frontend", "ai_agents/roles/frontend.md"),
    ("UI/UX", "ai_agents/roles/ui_ux.md"),
    ("Security", "ai_agents/roles/security.md"),
    ("Docs/Confluence", "ai_agents/roles/docs_confluence.md"),
    ("DevOps/Platform", "ai_agents/roles/devops_platform.md"),
    ("Data/Persistence", "ai_agents/roles/data_persistence.md"),
)


def test_session_mode_validation_playbook_covers_all_session_roles(project_root: Path) -> None:
    playbook = (project_root / "docs" / "session-mode-validation-playbook.md").read_text(
        encoding="utf-8"
    )

    for role, role_file in ROLE_SECTIONS:
        assert f"`## {role}`" in playbook
        assert f"`{role_file}`" in playbook


def test_session_mode_validation_playbook_defines_role_outputs_and_stop_conditions(
    project_root: Path,
) -> None:
    playbook = (project_root / "docs" / "session-mode-validation-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "| Role | Startup prompt | Role file | Expected outputs | Stop conditions |" in playbook

    table_rows = [line for line in playbook.splitlines() if line.startswith("| ")][2:]
    role_rows = [line for line in table_rows if "ai_agents/roles/" in line]

    assert len(role_rows) == len(ROLE_SECTIONS)
    for row in role_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 5
        assert cells[3]
        assert cells[4]


def test_session_mode_validation_playbook_feeds_docker_requirements_and_future_stories(
    project_root: Path,
) -> None:
    playbook = (project_root / "docs" / "session-mode-validation-playbook.md").read_text(
        encoding="utf-8"
    )

    required_references = (
        "data/agent-logs/<JIRA_ISSUE>/",
        "docs/docker-worker-requirements.md",
        "docs/docker-worker-readiness.md",
        "docs/docker-worker-triggering.md",
        "docs/parallel-agent-workspaces.md",
        "FUNNEL",
        "PO inbox",
    )

    for reference in required_references:
        assert reference in playbook


def test_session_mode_validation_playbook_requires_limit_and_dependency_checks(
    project_root: Path,
) -> None:
    playbook = (project_root / "docs" / "session-mode-validation-playbook.md").read_text(
        encoding="utf-8"
    )

    assert "agentic codex-limits latest" in playbook
    assert "agentic setup validate --project-root ." in playbook
    assert "Validate Jira status and dependency eligibility" in playbook
