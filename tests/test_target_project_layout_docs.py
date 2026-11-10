from pathlib import Path


def test_target_project_layout_documents_source_and_platform_boundaries(project_root: Path) -> None:
    layout = (project_root / "docs" / "target-project-layout.md").read_text(encoding="utf-8")
    getting_started = (project_root / "docs" / "getting-started.md").read_text(encoding="utf-8")
    credential_setup = (project_root / "docs" / "credential-setup.md").read_text(encoding="utf-8")

    for folder in (
        "docs/product/",
        "docs/architecture/",
        "docs/nfr/",
        "docs/release-scope/",
        "docs/samples/",
        "docs/decisions/",
    ):
        assert folder in layout

    assert "The PO inbox is explicitly platform-owned." in layout
    assert "Backlog drafts and generated planning bundles default to platform durable data." in layout
    assert "Do not store platform runtime state inside the target project checkout." in layout
    assert "Treat these as setup errors" in layout
    assert "TARGET_PROJECT_PATH" in layout
    assert "data/po-inbox/" in layout
    assert "data/context-packs/" in layout
    assert "data/codex-jobs/" in layout
    assert "data/codex-results/" in layout

    assert "docs/target-project-layout.md" in getting_started
    assert "docs/target-project-layout.md" in credential_setup
