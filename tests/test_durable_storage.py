from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.storage import durable_directories, initialize_durable_directories


def test_durable_directories_match_configured_contract(tmp_path: Path) -> None:
    settings = _settings_with_temp_paths(tmp_path)

    directories = durable_directories(settings.paths)

    assert [directory.name for directory in directories] == [
        "po_inbox",
        "context_packs",
        "codex_jobs",
        "codex_results",
        "codex_limits",
        "agent_state",
        "agent_logs",
        "po_decisions",
        "sprints",
        "confluence_mirror",
    ]
    assert [directory.path.name for directory in directories] == [
        "po-inbox",
        "context-packs",
        "codex-jobs",
        "codex-results",
        "codex-limits",
        "agent-state",
        "agent-logs",
        "po-decisions",
        "sprints",
        "confluence-mirror",
    ]


def test_initialize_durable_directories_is_idempotent(tmp_path: Path) -> None:
    settings = _settings_with_temp_paths(tmp_path)

    first_result = initialize_durable_directories(settings)
    second_result = initialize_durable_directories(settings)

    assert first_result == second_result
    assert all(directory.path.is_dir() for directory in first_result)
    assert all(directory.path.parent == tmp_path for directory in first_result)


def _settings_with_temp_paths(tmp_path: Path):
    return settings_from_mapping(
        {
            "DURABLE_PO_INBOX_PATH": str(tmp_path / "po-inbox"),
            "DURABLE_CONTEXT_PACKS_PATH": str(tmp_path / "context-packs"),
            "DURABLE_CODEX_JOBS_PATH": str(tmp_path / "codex-jobs"),
            "DURABLE_CODEX_RESULTS_PATH": str(tmp_path / "codex-results"),
            "DURABLE_CODEX_LIMITS_PATH": str(tmp_path / "codex-limits"),
            "DURABLE_AGENT_STATE_PATH": str(tmp_path / "agent-state"),
            "DURABLE_AGENT_LOGS_PATH": str(tmp_path / "agent-logs"),
            "DURABLE_PO_DECISIONS_PATH": str(tmp_path / "po-decisions"),
            "DURABLE_SPRINTS_PATH": str(tmp_path / "sprints"),
            "DURABLE_CONFLUENCE_MIRROR_PATH": str(tmp_path / "confluence-mirror"),
        }
    )
