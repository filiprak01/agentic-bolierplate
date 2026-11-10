from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    DEFAULT_DOCS_SITE_NAV,
    build_docs_site,
    docs_site_build_to_dict,
    docs_site_validation_to_dict,
    validate_docs_site,
)


def test_default_docs_site_navigation_covers_po_agents_release_and_evidence() -> None:
    nav_paths = {item.path for item in DEFAULT_DOCS_SITE_NAV}
    audiences = {item.audience for item in DEFAULT_DOCS_SITE_NAV}

    assert "index.md" in nav_paths
    assert "operator-ui.md" in nav_paths
    assert "ai-documentation-index.md" in nav_paths
    assert "release-notes/release-1.2.0.md" in nav_paths
    assert "release-1.2-operator-guide.md" in nav_paths
    assert "release-1.2-migration-guide.md" in nav_paths
    assert "release-1.2-closure-package.md" in nav_paths
    assert "shared-evidence-publication-policy.md" in nav_paths
    assert "reports/index.md" in nav_paths
    assert "evidence-publication-helper.md" in nav_paths
    assert {"po_readable", "ai_first_internal", "partner_report"} <= audiences


def test_validate_docs_site_checks_required_paths_and_links(project_root: Path) -> None:
    result = validate_docs_site(project_root / "docs")

    assert result.passed
    assert not result.missing_paths
    assert not result.broken_links
    payload = docs_site_validation_to_dict(result)
    assert payload["passed"] is True
    assert "ai-documentation-index.md" in payload["required_paths"]


def test_build_docs_site_writes_static_html_preview(project_root: Path, tmp_path: Path) -> None:
    output_root = tmp_path / "site"

    result = build_docs_site(project_root / "docs", output_root)

    assert result.validation.passed
    assert (output_root / "index.html").is_file()
    assert (output_root / "ai-documentation-index.html").is_file()
    index = (output_root / "index.html").read_text(encoding="utf-8")
    assert "<nav>" in index
    assert "Agentic Boilerplate Documentation" in index
    assert "AI Documentation Index" in index
    assert docs_site_build_to_dict(result)["written_files"]


def test_docs_site_cli_validate_and_build(project_root: Path, tmp_path: Path, capsys) -> None:
    docs_root = project_root / "docs"
    output_root = tmp_path / "site"

    assert main(["docs-site", "validate", "--docs-root", str(docs_root), "--json"]) == 0
    assert '"passed": true' in capsys.readouterr().out

    assert (
        main(
            [
                "docs-site",
                "build",
                "--docs-root",
                str(docs_root),
                "--output-root",
                str(output_root),
                "--json",
            ]
        )
        == 0
    )
    assert (output_root / "index.html").is_file()
    assert '"written_files"' in capsys.readouterr().out
