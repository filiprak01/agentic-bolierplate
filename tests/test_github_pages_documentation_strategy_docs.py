from pathlib import Path


def test_github_pages_strategy_defines_default_and_confluence_fallback(project_root: Path) -> None:
    strategy = (project_root / "docs" / "github-pages-documentation-strategy.md").read_text(encoding="utf-8")

    required_phrases = (
        "local Markdown in Git the editable documentation source of truth",
        "GitHub Pages the default published documentation and report view",
        "Confluence remains an optional secondary publication target",
        "`github_pages`",
        "Setup validation must not block default project readiness because",
    )

    for phrase in required_phrases:
        assert phrase in strategy


def test_github_pages_strategy_classifies_publication_audiences(project_root: Path) -> None:
    strategy = (project_root / "docs" / "github-pages-documentation-strategy.md").read_text(encoding="utf-8")

    for publication_class in (
        "`ai_first_internal`",
        "`po_readable`",
        "`partner_report`",
        "`internal_only`",
    ):
        assert publication_class in strategy

    assert "Documentation changes require a Jira story or task and a pull request" in strategy
    assert "Docs-only release notes may be created without a new implementation story" in strategy


def test_governance_confluence_and_setup_docs_reference_strategy(project_root: Path) -> None:
    strategy_ref = "docs/github-pages-documentation-strategy.md"
    governance = (project_root / "docs" / "documentation-governance.md").read_text(encoding="utf-8")
    confluence = (project_root / "docs" / "confluence-adapter.md").read_text(encoding="utf-8")
    getting_started = (project_root / "docs" / "getting-started.md").read_text(encoding="utf-8")

    assert strategy_ref in governance
    assert strategy_ref in confluence
    assert "GitHub Pages" in governance
    assert "Confluence publication is optional" in governance
    assert "missing Confluence credentials must not block default project setup" in confluence
    assert "Release 1.2 defaults to GitHub Pages" in getting_started
