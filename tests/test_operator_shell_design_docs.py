from pathlib import Path


DESIGN_DOC = Path("docs/design/operator-shell-navigation-design.md")
DESIGN_HTML = Path("docs/design/operator-shell-navigation-options.html")


def test_operator_shell_design_documents_selected_option_and_design_reference() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")

    assert "AGENT-669" in text
    assert "Selected option: Option B - Compact Header With Hamburger Drawer" in text
    assert "Design Reference:" in text
    assert "AGENT-665" in text
    assert "PO acceptance note:" in text
    assert "Jira propagation:" in text


def test_operator_shell_design_html_contains_two_options_and_critical_sections() -> None:
    text = DESIGN_HTML.read_text(encoding="utf-8")

    assert "Option A" in text
    assert "Option B" in text
    assert "Persistent Rail" in text
    assert "Compact Header With Drawer" in text
    assert "PO Inbox" in text
    assert "Codex Limits" in text
    assert "Workers" in text
    assert "Logs" in text
    assert "Projects" in text
    assert "Agent Messages" in text
    assert "3 blockers" in text
    assert "API connected" in text


def test_operator_shell_design_artifacts_are_ascii_safe() -> None:
    for path in (DESIGN_DOC, DESIGN_HTML):
        path.read_text(encoding="ascii")
