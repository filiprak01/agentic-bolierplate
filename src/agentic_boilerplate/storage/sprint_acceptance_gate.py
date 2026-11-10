"""Durable sprint gate decision logs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.domain.sprint_acceptance_gate import (
    GateDecision,
    render_gate_decision_log,
)


def write_gate_decision_log(
    decision: GateDecision,
    directory: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Persist a scheduler or release-manager gate decision log."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=True)
    safe_issue_key = decision.issue_key.replace(" ", "-")
    path = directory / f"{safe_issue_key}-{decision.decision_type.value}-{timestamp}.md"
    path.write_text(render_gate_decision_log(decision), encoding="utf-8")
    return path
