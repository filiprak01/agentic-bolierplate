from pathlib import Path


DESIGN_DOC = Path("docs/design/compact-po-inbox-ux-design.md")
DESIGN_HTML = Path("docs/design/compact-po-inbox-ux-options.html")


def test_compact_po_inbox_design_documents_selected_option_and_references() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    assert "AGENT-667" in text
    assert "Selected option: Option A - Compact Split Pane With Sticky Action Dock" in text
    assert "Implementation references: AGENT-637, AGENT-672, AGENT-664, AGENT-638" in text
    assert "Design Reference:" in text
    assert "PO Acceptance Note" in text


def test_compact_po_inbox_design_html_contains_two_options_and_required_states() -> None:
    text = DESIGN_HTML.read_text(encoding="utf-8")

    for label in (
        "Option A - Split Pane With Sticky Action Dock",
        "Option B - Queue First With Drawer Detail",
        "All Projects",
        "Export JSON",
        "Export selected",
        "Per-project error",
        "Loading",
        "Empty",
        "Answered",
        "Failed API",
        "Many items",
        "Decision text",
    ):
        assert label in text


def test_operator_ui_docs_reference_compact_po_inbox_design(project_root: Path) -> None:
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert "AGENT-667" in docs
    assert "docs/design/compact-po-inbox-ux-design.md" in docs
    assert "Option A - Compact Split Pane With Sticky Action Dock" in docs
    assert "AGENT-637 and AGENT-672 must reference the AGENT-667 inbox design" in docs


def test_compact_po_inbox_design_artifacts_are_ascii_safe() -> None:
    for path in (DESIGN_DOC, DESIGN_HTML):
        path.read_text(encoding="ascii")
