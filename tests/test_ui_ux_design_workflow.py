from pathlib import Path


def test_ui_ux_design_workflow_defines_required_handoff_artifacts(project_root: Path) -> None:
    workflow = (project_root / "docs" / "ui-ux-design-workflow.md").read_text(encoding="utf-8")

    for required in (
        "Target user and primary workflow summary",
        "Screen or route list",
        "User flow or interaction notes",
        "Layout, responsive, and accessibility expectations",
        "Copy or copy-decision placeholders",
        "Design handoff reference",
    ):
        assert required in workflow

    assert "Frontend stories can reference these artifacts" in workflow
    assert "without requiring paid Figma API usage" in workflow


def test_ui_ux_design_workflow_sets_figma_baseline_and_automation_gate(project_root: Path) -> None:
    workflow = (project_root / "docs" / "ui-ux-design-workflow.md").read_text(encoding="utf-8")
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")
    credentials = (project_root / "docs" / "credential-setup.md").read_text(encoding="utf-8")

    assert "Figma is the preferred UI/UX design and handoff tool" in workflow
    assert "Release 1.1 uses a manual Figma link/export workflow by default." in workflow
    assert "Automated Figma API or plugin integration must not be assumed." in workflow
    assert "design_references" in workflow
    assert "FIGMA_EXPORTS_PATH=docs/design" in env_example
    assert "Figma access is optional." in credentials

    for gate in (
        "Figma workspace access",
        "API or plugin availability",
        "Cost or paid-plan impact",
        "Permission model",
    ):
        assert gate in workflow

    assert "create a PO inbox" in workflow


def test_ui_ux_roles_reference_design_workflow_and_po_question_triggers(project_root: Path) -> None:
    ui_ux = (project_root / "ai_agents" / "roles" / "ui_ux.md").read_text(encoding="utf-8")
    frontend = (project_root / "ai_agents" / "roles" / "frontend.md").read_text(encoding="utf-8")

    assert "docs/ui-ux-design-workflow.md" in ui_ux
    assert "docs/ui-ux-design-workflow.md" in frontend
    assert "Figma access" in ui_ux
    assert "paid tooling" in ui_ux
    assert "before implementation starts" in frontend
