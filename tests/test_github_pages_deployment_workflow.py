from pathlib import Path


def test_docs_pages_workflow_validates_on_pr_and_deploys_only_when_enabled(project_root: Path) -> None:
    workflow = (project_root / ".github" / "workflows" / "docs-pages.yml").read_text(encoding="utf-8")

    required_phrases = (
        "pull_request:",
        "PYTHONPATH=src python -m agentic_boilerplate.cli docs-site validate --docs-root docs",
        "PYTHONPATH=src python -m agentic_boilerplate.cli docs-site build --docs-root docs --output-root site",
        "actions/upload-artifact@v4",
        "vars.AGENTIC_DOCS_PUBLISH_ENABLED == 'true'",
        "github.event_name != 'pull_request'",
        "actions/deploy-pages@v4",
    )

    for phrase in required_phrases:
        assert phrase in workflow


def test_docs_pages_workflow_limits_publication_refs(project_root: Path) -> None:
    workflow = (project_root / ".github" / "workflows" / "docs-pages.yml").read_text(encoding="utf-8")

    assert "github.ref == 'refs/heads/main'" in workflow
    assert "startsWith(github.ref, 'refs/heads/release/')" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert 'branches:\n      - main\n      - "release/**"' in workflow
    assert 'tags:\n      - "v*"' in workflow


def test_github_pages_documentation_workflow_covers_release_and_redaction_rules(project_root: Path) -> None:
    docs = (project_root / "docs" / "github-pages-documentation-workflow.md").read_text(encoding="utf-8")

    for phrase in (
        "Pull requests never deploy",
        "AGENTIC_DOCS_PUBLISH_ENABLED=true",
        "Source set to GitHub Actions",
        "Release notes",
        "Sprint closure notes",
        "Regression summaries and manifests",
        "Partner reports after redaction and Product Owner approval",
        "The published site must not include:",
        "GitHub Pages URL",
    ):
        assert phrase in docs
