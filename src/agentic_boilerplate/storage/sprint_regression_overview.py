"""Durable Sprint regression overview plans."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.sprint_regression_overview import (
    SprintRegressionOverviewPlan,
    render_sprint_regression_overview_plan,
)


def write_sprint_regression_overview_plan(
    plan: SprintRegressionOverviewPlan,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a regression overview plan and return its path."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    safe_sprint = _safe_path_segment(plan.sprint_name)
    path = directory / f"sprint-regression-overview-{safe_sprint}-{timestamp}.md"
    path.write_text(render_sprint_regression_overview_plan(plan), encoding="utf-8")
    return path


def _safe_path_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "sprint"
