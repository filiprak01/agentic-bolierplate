from pathlib import Path


def test_github_pages_site_scaffold_documents_build_and_artifact_policy(project_root: Path) -> None:
    scaffold = (project_root / "docs" / "github-pages-site-scaffold.md").read_text(encoding="utf-8")
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

    required_phrases = (
        "Markdown-first static publication",
        "agentic docs-site validate --docs-root docs",
        "agentic docs-site build --docs-root docs --output-root site",
        "Existing docs remain usable as AI context",
        "Future multi-project report sections",
    )

    for phrase in required_phrases:
        assert phrase in scaffold

    assert "/site" in gitignore


def test_ai_documentation_index_maps_roles_and_workflows(project_root: Path) -> None:
    index = (project_root / "docs" / "ai-documentation-index.md").read_text(encoding="utf-8")

    for phrase in (
        "Every agent starts with:",
        "Product Planning",
        "Architecture",
        "Developer",
        "Review",
        "Tester",
        "Release Manager",
        "Docs Publication",
        "Load only the docs required for the current role",
    ):
        assert phrase in index
