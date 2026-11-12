from pathlib import Path

from agentic_boilerplate.domain.worker_instruction_bundle import platform_agents_instruction_path


def test_agents_md_documents_global_ui_design_gate(project_root: Path) -> None:
    content = platform_agents_instruction_path(project_root).read_text(encoding="utf-8")

    assert "## UI Design Gate" in content
    assert "must not start from a visual or interaction assumption" in content
    assert "Design Reference" in content
    assert "docs/ui-design-gate.md" in content


def test_role_instructions_enforce_design_gate(project_root: Path) -> None:
    roles = project_root / "ai_agents" / "roles"
    product_planning = (roles / "product_planning.md").read_text(encoding="utf-8")
    ui_ux = (roles / "ui_ux.md").read_text(encoding="utf-8")
    frontend = (roles / "frontend.md").read_text(encoding="utf-8")

    assert "Paired UI/UX design and frontend implementation stories" in product_planning
    assert "Jira `Blocks` dependency" in product_planning
    assert "accepted design reference" in ui_ux
    assert "accepted `Design Reference` section" in frontend
    assert "create a PO inbox question" in frontend


def test_ui_design_gate_doc_defines_story_pairing_and_reference(project_root: Path) -> None:
    content = (project_root / "docs" / "ui-design-gate.md").read_text(encoding="utf-8")

    for phrase in (
        "Required Story Pairing",
        "Design Reference:",
        "Product Owner acceptance",
        "Accepted Design States",
        "DEV COMPLETED is not enough",
        "Scheduler/Orchestrator",
    ):
        assert phrase in content


def test_existing_workflow_docs_reference_design_gate(project_root: Path) -> None:
    paths = (
        project_root / "docs" / "ui-ux-design-workflow.md",
        project_root / "docs" / "jira-story-creation-workflow.md",
        project_root / "docs" / "scheduler-approved-scope-assignment.md",
        project_root / "docs" / "operator-ui.md",
        project_root / "docs" / "definition-of-ready-gate.md",
    )

    for path in paths:
        assert "ui-design-gate" in path.read_text(encoding="utf-8")
