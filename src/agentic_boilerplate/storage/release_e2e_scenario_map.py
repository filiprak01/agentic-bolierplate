"""Durable release E2E scenario map storage."""

from __future__ import annotations

from pathlib import Path

from agentic_boilerplate.domain.release_e2e_scenario_map import (
    ReleaseE2EScenarioMap,
    render_release_e2e_scenario_map_markdown,
)


def write_release_e2e_scenario_map(
    scenario_map: ReleaseE2EScenarioMap,
    directory: Path,
) -> Path:
    """Persist a release E2E scenario map and return the markdown path."""

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_path_segment(scenario_map.release_key)}-e2e-scenario-map.md"
    path.write_text(render_release_e2e_scenario_map_markdown(scenario_map), encoding="utf-8")
    return path


def _safe_path_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "release"
