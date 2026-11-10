"""Durable local directory initialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.config import DurablePathSettings, PlatformSettings


@dataclass(frozen=True)
class DurableDirectory:
    name: str
    path: Path


def durable_directories(paths: DurablePathSettings) -> tuple[DurableDirectory, ...]:
    """Return the durable directory contract in stable order."""

    return (
        DurableDirectory("po_inbox", paths.po_inbox),
        DurableDirectory("context_packs", paths.context_packs),
        DurableDirectory("codex_jobs", paths.codex_jobs),
        DurableDirectory("codex_results", paths.codex_results),
        DurableDirectory("codex_limits", paths.codex_limits),
        DurableDirectory("agent_state", paths.agent_state),
        DurableDirectory("agent_logs", paths.agent_logs),
        DurableDirectory("po_decisions", paths.po_decisions),
        DurableDirectory("sprints", paths.sprints),
        DurableDirectory("confluence_mirror", paths.confluence_mirror),
    )


def initialize_durable_directories(settings: PlatformSettings) -> tuple[DurableDirectory, ...]:
    """Create all configured durable directories idempotently."""

    directories = durable_directories(settings.paths)
    for directory in directories:
        directory.path.mkdir(parents=True, exist_ok=True)
    return directories
