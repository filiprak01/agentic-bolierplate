"""Durable dependency eligibility assignment notes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.dependency_eligibility import (
    DependencyEligibilityResult,
    render_dependency_eligibility_note,
)


def write_dependency_eligibility_note(
    result: DependencyEligibilityResult,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a scheduler dependency note and return its path."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.issue_key}-dependency-eligibility-{timestamp}.md"
    path.write_text(render_dependency_eligibility_note(result), encoding="utf-8")
    return path
