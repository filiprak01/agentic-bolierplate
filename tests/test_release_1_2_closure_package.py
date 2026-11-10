from pathlib import Path


def test_release_1_2_operator_and_migration_guides_cover_required_setup(project_root: Path) -> None:
    operator = (project_root / "docs" / "release-1.2-operator-guide.md").read_text(encoding="utf-8")
    migration = (project_root / "docs" / "release-1.2-migration-guide.md").read_text(encoding="utf-8")

    for phrase in (
        "worker workspace root must not be inside the mutable source checkout",
        "Record current Codex limit availability",
        "GitHub Pages",
    ):
        assert phrase in operator

    for phrase in (
        "Back up the durable data folder",
        "TARGET_PROJECT_PATH",
        "AGENTIC_WORKSPACES_ROOT",
        "agentic setup validate",
    ):
        assert phrase in migration


def test_release_1_2_notes_and_closure_package_reference_sprint_6_evidence(project_root: Path) -> None:
    notes = (project_root / "docs" / "release-notes" / "release-1.2.0.md").read_text(encoding="utf-8")
    closure = (project_root / "docs" / "release-1.2-closure-package.md").read_text(encoding="utf-8")

    for phrase in (
        "Documentation repo slimming and archive policy",
        "Detached worker pilot evidence",
        "Review Agent approval publication fallback diagnostics",
    ):
        assert phrase in notes

    for key in ("AGENT-644", "AGENT-645", "AGENT-646", "AGENT-751"):
        assert key in closure

    assert "branch/tag checklist" in closure
