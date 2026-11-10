"""Durable delivery-state consistency reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.delivery_state_consistency import (
    DeliveryStateConsistencyReport,
    render_delivery_state_consistency_report,
)


def write_delivery_state_consistency_report(
    report: DeliveryStateConsistencyReport,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a delivery-state consistency report and return its path."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    safe_sprint = _safe_path_segment(report.sprint_name)
    path = directory / f"delivery-state-consistency-{safe_sprint}-{timestamp}.md"
    path.write_text(render_delivery_state_consistency_report(report), encoding="utf-8")
    return path


def _safe_path_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "sprint"
