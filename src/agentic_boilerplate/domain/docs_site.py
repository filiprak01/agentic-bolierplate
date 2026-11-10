"""GitHub Pages documentation site scaffold and validation."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DocsSiteError(ValueError):
    """Raised when docs site scaffold validation fails."""


@dataclass(frozen=True)
class DocsSiteNavItem:
    title: str
    path: str
    audience: str


@dataclass(frozen=True)
class DocsSiteValidationResult:
    docs_root: str
    required_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    broken_links: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_paths and not self.broken_links


@dataclass(frozen=True)
class DocsSiteBuildResult:
    docs_root: str
    output_root: str
    written_files: tuple[str, ...]
    validation: DocsSiteValidationResult


DEFAULT_DOCS_SITE_NAV: tuple[DocsSiteNavItem, ...] = (
    DocsSiteNavItem("Product Owner Overview", "index.md", "po_readable"),
    DocsSiteNavItem("Getting Started", "getting-started.md", "po_readable"),
    DocsSiteNavItem("PO Inbox And Operator UI", "operator-ui.md", "po_readable"),
    DocsSiteNavItem("Agent Roles", "ai-documentation-index.md", "ai_first_internal"),
    DocsSiteNavItem("Workflow Map", "story-processing-path-matrix.md", "ai_first_internal"),
    DocsSiteNavItem("Release 1.2 Notes", "release-notes/release-1.2.0.md", "po_readable"),
    DocsSiteNavItem("Release 1.2 Operator Guide", "release-1.2-operator-guide.md", "po_readable"),
    DocsSiteNavItem("Release 1.2 Migration Guide", "release-1.2-migration-guide.md", "po_readable"),
    DocsSiteNavItem("Release 1.2 Closure Package", "release-1.2-closure-package.md", "partner_report"),
    DocsSiteNavItem("Published Reports", "reports/index.md", "partner_report"),
    DocsSiteNavItem("Evidence Publication", "shared-evidence-publication-policy.md", "partner_report"),
    DocsSiteNavItem("Report Publication Helper", "evidence-publication-helper.md", "ai_first_internal"),
)


def validate_docs_site(
    docs_root: str | Path,
    *,
    nav_items: tuple[DocsSiteNavItem, ...] = DEFAULT_DOCS_SITE_NAV,
) -> DocsSiteValidationResult:
    """Validate required docs site paths and local markdown links."""

    root = Path(docs_root)
    required_paths = tuple(item.path for item in nav_items)
    required_paths += (
        "github-pages-documentation-strategy.md",
        "github-pages-site-scaffold.md",
        "site-navigation.md",
    )
    missing_paths = tuple(path for path in required_paths if not (root / path).is_file())
    broken_links: list[str] = []
    for relative_path in required_paths:
        path = root / relative_path
        if not path.is_file():
            continue
        for link in _markdown_links(path.read_text(encoding="utf-8")):
            if _is_external_or_anchor(link):
                continue
            target_fragment = link.split("#", 1)[0]
            if not target_fragment:
                continue
            target = (path.parent / target_fragment).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                broken_links.append(f"{relative_path}: {link} escapes docs root")
                continue
            if not target.exists():
                broken_links.append(f"{relative_path}: {link}")
    return DocsSiteValidationResult(
        docs_root=str(root),
        required_paths=required_paths,
        missing_paths=missing_paths,
        broken_links=tuple(broken_links),
    )


def build_docs_site(
    docs_root: str | Path,
    output_root: str | Path,
    *,
    nav_items: tuple[DocsSiteNavItem, ...] = DEFAULT_DOCS_SITE_NAV,
) -> DocsSiteBuildResult:
    """Build a lightweight static HTML docs site from selected Markdown files."""

    validation = validate_docs_site(docs_root, nav_items=nav_items)
    if not validation.passed:
        raise DocsSiteError("Docs site validation failed.")
    docs_path = Path(docs_root)
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    navigation = _render_navigation(nav_items)
    for item in nav_items:
        source = docs_path / item.path
        html_path = output_path / Path(item.path).with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            _html_page(
                title=item.title,
                navigation=navigation,
                body=_render_markdown(source.read_text(encoding="utf-8")),
            ),
            encoding="utf-8",
        )
        written.append(str(html_path))
    return DocsSiteBuildResult(
        docs_root=str(docs_path),
        output_root=str(output_path),
        written_files=tuple(written),
        validation=validation,
    )


def docs_site_validation_to_dict(result: DocsSiteValidationResult) -> dict[str, Any]:
    return {
        "docs_root": result.docs_root,
        "required_paths": list(result.required_paths),
        "missing_paths": list(result.missing_paths),
        "broken_links": list(result.broken_links),
        "passed": result.passed,
    }


def docs_site_build_to_dict(result: DocsSiteBuildResult) -> dict[str, Any]:
    return {
        "docs_root": result.docs_root,
        "output_root": result.output_root,
        "written_files": list(result.written_files),
        "validation": docs_site_validation_to_dict(result.validation),
    }


def _markdown_links(text: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text))


def _is_external_or_anchor(link: str) -> bool:
    return link.startswith(("#", "http://", "https://", "mailto:"))


def _render_navigation(nav_items: tuple[DocsSiteNavItem, ...]) -> str:
    links = "\n".join(
        f'<li><a href="{html.escape(Path(item.path).with_suffix(".html").as_posix())}">'
        f"{html.escape(item.title)}</a></li>"
        for item in nav_items
    )
    return f"<nav><strong>Agentic Docs</strong><ul>{links}</ul></nav>"


def _render_markdown(text: str) -> str:
    lines: list[str] = []
    in_list = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("### "):
            lines.append(_close_list(in_list))
            in_list = False
            lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            lines.append(_close_list(in_list))
            in_list = False
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            lines.append(_close_list(in_list))
            in_list = False
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith(("- ", "* ")):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif not line:
            lines.append(_close_list(in_list))
            in_list = False
        else:
            lines.append(_close_list(in_list))
            in_list = False
            lines.append(f"<p>{html.escape(line)}</p>")
    lines.append(_close_list(in_list))
    return "\n".join(line for line in lines if line)


def _close_list(in_list: bool) -> str:
    return "</ul>" if in_list else ""


def _html_page(*, title: str, navigation: str, body: str) -> str:
    return "\n".join(
        (
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(title)} - Agentic Boilerplate</title>",
            "<style>",
            "body{font-family:system-ui,sans-serif;margin:0;display:grid;grid-template-columns:18rem 1fr;min-height:100vh}",
            "nav{background:#f5f7fb;border-right:1px solid #d8dee9;padding:1rem;position:sticky;top:0;height:100vh;box-sizing:border-box;overflow:auto}",
            "main{padding:2rem;max-width:60rem}",
            "a{color:#0b5cad} li{margin:.35rem 0} code{background:#eef2f7;padding:.1rem .25rem}",
            "@media(max-width:760px){body{display:block}nav{position:static;height:auto;border-right:0;border-bottom:1px solid #d8dee9}main{padding:1rem}}",
            "</style>",
            "</head>",
            "<body>",
            navigation,
            f"<main>{body}</main>",
            "</body>",
            "</html>",
        )
    )
