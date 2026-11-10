from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def src_root(project_root: Path) -> Path:
    return project_root / "src"


@pytest.fixture
def minimal_required_env() -> dict[str, str]:
    return {
        "GITHUB_TOKEN": "test-github-token",
        "JIRA_EMAIL": "po@example.com",
        "JIRA_API_TOKEN": "test-jira-token",
    }
