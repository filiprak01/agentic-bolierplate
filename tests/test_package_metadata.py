import re
from pathlib import Path

import agentic_boilerplate


def test_package_metadata_matches_current_project_version(project_root: Path) -> None:
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    readme = (project_root / "README.md").read_text(encoding="utf-8")

    project_version = _project_version(pyproject)

    assert agentic_boilerplate.__version__ == project_version
    assert f"Package metadata version: `{project_version}`." in readme


def test_mvp_release_notes_keep_original_release_version(project_root: Path) -> None:
    release_notes = (project_root / "docs" / "release-notes" / "mvp-release-1.md").read_text(encoding="utf-8")

    assert "Version: `1.0.0`" in release_notes


def _project_version(pyproject: str) -> str:
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert match is not None
    return match.group(1)
