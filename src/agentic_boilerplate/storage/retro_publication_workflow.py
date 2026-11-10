"""Durable sprint retro publication workflow plans."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.retro_publication_workflow import (
    SprintPublicationPlan,
    render_sprint_publication_plan,
)


def write_sprint_publication_plan(
    plan: SprintPublicationPlan,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a sprint publication plan and return its path."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    safe_sprint = _safe_path_segment(plan.sprint_name)
    path = directory / f"sprint-publication-plan-{safe_sprint}-{timestamp}.md"
    path.write_text(render_sprint_publication_plan(plan), encoding="utf-8")
    return path


def _safe_path_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "sprint"
