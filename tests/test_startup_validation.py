from pathlib import Path

import pytest

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.runtime import (
    StartupDiagnosticCategory,
    StartupRepairAction,
    StartupValidationError,
    build_worker_startup_message,
    format_startup_checklist,
    require_startup_ready,
    startup_validation_to_dict,
    validate_startup,
)


def test_startup_validation_passes_with_required_config_and_writable_paths(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path)

    result = validate_startup(settings)

    assert result.passed
    assert not result.failed_checks
    assert all((tmp_path / name).is_dir() for name in _durable_folder_names())


def test_startup_validation_reports_missing_required_config_without_values(tmp_path: Path) -> None:
    settings = settings_from_mapping(
        {
            "DURABLE_PO_INBOX_PATH": str(tmp_path / "po-inbox"),
        }
    )

    result = validate_startup(settings)
    checklist = format_startup_checklist(result)

    assert not result.passed
    assert "configuration.github.token" in checklist
    assert "configuration.jira.api_token" in checklist
    assert "workers.target_project_path" in checklist
    assert "secret" not in checklist.lower()


def test_require_startup_ready_raises_checklist_error(tmp_path: Path) -> None:
    settings = settings_from_mapping({})

    with pytest.raises(StartupValidationError) as exc_info:
        require_startup_ready(settings)

    assert "Startup validation checklist" in str(exc_info.value)


def test_startup_validation_rejects_invalid_worker_roles(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path, extra={"WORKER_ROLES": "developer,invalid_role"})

    result = validate_startup(settings)

    assert not result.passed
    assert any(check.name == "workers.roles" for check in result.failed_checks)


def test_startup_validation_requires_target_project_path(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path, extra={"TARGET_PROJECT_PATH": ""})

    result = validate_startup(settings)

    assert not result.passed
    assert any(check.name == "workers.target_project_path" for check in result.failed_checks)


def test_startup_validation_rejects_missing_target_project_directory(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path, extra={"TARGET_PROJECT_PATH": str(tmp_path / "missing-project")})

    result = validate_startup(settings)

    assert not result.passed
    assert any(check.name == "workers.target_project_path" for check in result.failed_checks)


def test_startup_validation_rejects_target_project_without_git_metadata(tmp_path: Path) -> None:
    plain_project = tmp_path / "plain-project"
    plain_project.mkdir()
    settings = _valid_settings(tmp_path, extra={"TARGET_PROJECT_PATH": str(plain_project)})

    result = validate_startup(settings)

    assert not result.passed
    failure = next(check for check in result.failed_checks if check.name == "workers.target_project_path.git_metadata")
    assert failure.category is StartupDiagnosticCategory.REPOSITORY
    assert failure.repair_action is StartupRepairAction.MANUAL_REPAIR_REQUIRED


def test_startup_validation_fails_when_durable_path_is_not_directory(tmp_path: Path) -> None:
    blocked_path = tmp_path / "not-a-directory"
    blocked_path.write_text("not a directory", encoding="utf-8")
    settings = _valid_settings(tmp_path, extra={"DURABLE_PO_INBOX_PATH": str(blocked_path)})

    result = validate_startup(settings)

    assert not result.passed
    assert any(check.name == "paths.create" for check in result.failed_checks)


def test_startup_validation_checks_po_inbox_status_directories(tmp_path: Path) -> None:
    po_inbox = tmp_path / "po-inbox"
    answered = po_inbox / "answered"
    answered.mkdir(parents=True)
    answered.chmod(0o555)
    settings = _valid_settings(tmp_path, extra={"DURABLE_PO_INBOX_PATH": str(po_inbox)})

    try:
        result = validate_startup(settings)
    finally:
        answered.chmod(0o755)

    assert not result.passed
    assert any(check.name == "paths.po_inbox.answered.writable" for check in result.failed_checks)


def test_startup_validation_records_allowlisted_directory_repairs(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path)

    result = validate_startup(settings)

    assert result.passed
    assert any(check.repair_action is StartupRepairAction.CREATE_DIRECTORY for check in result.repair_actions)
    assert any(
        check.repair_action is StartupRepairAction.ENSURE_PO_INBOX_STATUS_DIRECTORIES
        for check in result.repair_actions
    )


def test_startup_validation_blocks_api_token_when_subscription_gateway_enabled(tmp_path: Path) -> None:
    settings = _valid_settings(
        tmp_path,
        extra={
            "CODEX_LIMIT_SENTINEL_ENABLED": "true",
            "CODEX_ACCESS_TOKEN": "secret-codex-api-token",
        },
    )

    result = validate_startup(settings)
    checklist = format_startup_checklist(result)
    diagnostics = startup_validation_to_dict(result)

    assert not result.passed
    failure = next(check for check in result.failed_checks if check.name == "codex.auth_mode")
    assert failure.category is StartupDiagnosticCategory.AUTHENTICATION
    assert "secret-codex-api-token" not in checklist
    assert "secret-codex-api-token" not in str(diagnostics)


def test_startup_validation_can_run_optional_integration_probes(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path)

    result = validate_startup(
        settings,
        check_integrations=True,
        integration_probes={
            "github": lambda: True,
            "jira": lambda: False,
            "confluence": lambda: True,
        },
    )

    assert not result.passed
    assert any(check.name == "integrations.jira" for check in result.failed_checks)
    assert "Integration access check failed" in format_startup_checklist(result)


def test_startup_validation_classifies_connector_authorization_failures(tmp_path: Path) -> None:
    def forbidden_probe() -> bool:
        raise RuntimeError("HTTP 403 organization SSO required for hidden token value")

    settings = _valid_settings(tmp_path)

    result = validate_startup(
        settings,
        check_integrations=True,
        integration_probes={
            "github": forbidden_probe,
            "jira": lambda: True,
            "confluence": lambda: True,
        },
    )

    assert not result.passed
    failure = next(check for check in result.failed_checks if check.name == "integrations.github")
    assert failure.category is StartupDiagnosticCategory.AUTHORIZATION
    assert "hidden token value" not in format_startup_checklist(result)


def test_startup_validation_skips_missing_optional_probe(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path)

    result = validate_startup(settings, check_integrations=True, integration_probes={})

    assert result.passed
    assert "Integration access check was skipped" in format_startup_checklist(result)


def test_worker_startup_message_contains_role_context() -> None:
    message = build_worker_startup_message(
        AgentRole.DEVELOPER,
        instruction_root="/workspace/platform",
        assignment_context_pack_path="/workspace/data/context-packs/AP-29.json",
        project_id="AP",
        jira_issue_key="AP-29",
        repository="example-org/ap-project",
        worker_id="developer-1",
    )

    assert "Read AGENTS.md first." in message
    assert "Act as developer Agent" in message
    assert "developer.md" in message
    assert "/workspace/data/context-packs/AP-29.json" in message
    assert "Project id: AP." in message
    assert "Jira issue: AP-29." in message
    assert "Worker id: developer-1." in message


def test_startup_validation_reports_github_pages_default_without_confluence_requirement(tmp_path: Path) -> None:
    settings = _valid_settings(
        tmp_path,
        extra={
            "DOCUMENTATION_PROVIDER": "github_pages",
            "GITHUB_PAGES_DOCS_URL": "",
            "GITHUB_PAGES_SOURCE_DIR": "docs",
        },
    )

    result = validate_startup(settings)
    checklist = format_startup_checklist(result)

    assert result.passed
    assert "documentation.provider" in checklist
    assert "GitHub Pages is the default documentation publication provider." in checklist
    assert "GitHub Pages URL is not configured yet" in checklist
    assert "documentation.confluence.required" not in checklist


def test_startup_validation_supports_confluence_both_and_offline_provider_modes(tmp_path: Path) -> None:
    confluence = validate_startup(_valid_settings(tmp_path, extra={"DOCUMENTATION_PROVIDER": "confluence"}))
    both = validate_startup(_valid_settings(tmp_path, extra={"DOCUMENTATION_PROVIDER": "both"}))
    offline = validate_startup(_valid_settings(tmp_path, extra={"DOCUMENTATION_PROVIDER": "offline"}))

    assert confluence.passed
    assert both.passed
    assert offline.passed
    assert "Confluence is selected as the documentation provider." in format_startup_checklist(confluence)
    assert "GitHub Pages and Confluence are both selected" in format_startup_checklist(both)
    assert "offline/local-only" in format_startup_checklist(offline)


def test_startup_validation_rejects_invalid_documentation_provider(tmp_path: Path) -> None:
    settings = _valid_settings(tmp_path, extra={"DOCUMENTATION_PROVIDER": "wiki"})

    result = validate_startup(settings)

    assert not result.passed
    assert any(check.name == "configuration.documentation.provider" for check in result.failed_checks)
    assert any(check.name == "documentation.provider" for check in result.failed_checks)


def _valid_settings(tmp_path: Path, *, extra: dict[str, str] | None = None):
    target_project = tmp_path / "target-project"
    target_project.mkdir(exist_ok=True)
    (target_project / ".git").mkdir(exist_ok=True)
    values = {
        "GITHUB_TOKEN": "github-token",
        "GITHUB_REPOSITORY": "example-org/agentic-boilerplate",
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_PROJECT_KEY": "AGENT",
        "JIRA_BOARD_ID": "1",
        "JIRA_EMAIL": "po@example.com",
        "JIRA_API_TOKEN": "jira-token",
        "CONFLUENCE_BASE_URL": "https://example.atlassian.net/wiki",
        "CONFLUENCE_SPACE_KEY": "AGENT",
        "CONFLUENCE_PARENT_PAGE_ID": "123",
        "CONFLUENCE_EMAIL": "po@example.com",
        "CONFLUENCE_API_TOKEN": "confluence-token",
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
        "TARGET_PROJECT_PATH": str(target_project),
    }
    if extra:
        values.update(extra)
    return settings_from_mapping(values)


def _durable_folder_names() -> tuple[str, ...]:
    return (
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
    )
