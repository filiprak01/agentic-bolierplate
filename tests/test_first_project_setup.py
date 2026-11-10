from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain import (
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
)
from agentic_boilerplate.domain.first_project_setup import (
    format_first_project_setup_validation,
    validate_first_project_setup,
)


def test_first_project_setup_passes_with_configured_project_and_limit_record(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(
        _settings(project_root, target_project),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert result.passed
    assert not result.failed_checks
    checklist = format_first_project_setup_validation(result)
    assert "target_project.agents_template" in checklist
    assert "docs/templates/target-project-AGENTS.md" in checklist


def test_first_project_setup_reports_missing_limit_record_without_secrets(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(_settings(project_root, target_project), project_root=project_root)
    checklist = format_first_project_setup_validation(result)

    assert not result.passed
    assert "codex_limits.latest" in checklist
    assert "ask_product_owner" in checklist
    assert "secret" not in checklist.lower()
    assert "github-token" not in checklist
    assert "agiletest-token" not in checklist


def test_first_project_setup_applies_configured_limit_timestamp_policy(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()
    settings = _settings(
        project_root,
        target_project,
        extra={
            "CODEX_LIMIT_STALE_AFTER_SECONDS": "300",
            "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS": "30",
        },
    )
    now = datetime.now(UTC).replace(microsecond=0)

    fresh = validate_first_project_setup(
        settings,
        project_root=project_root,
        latest_limit_record=_available_limit_record_at(now - timedelta(seconds=60)),
    )
    stale = validate_first_project_setup(
        settings,
        project_root=project_root,
        latest_limit_record=_available_limit_record_at(now - timedelta(seconds=600)),
    )
    future = validate_first_project_setup(
        settings,
        project_root=project_root,
        latest_limit_record=_available_limit_record_at(now + timedelta(seconds=120)),
    )
    invalid = validate_first_project_setup(
        settings,
        project_root=project_root,
        latest_limit_record=_available_limit_record_at("not-a-timestamp"),
    )

    assert fresh.passed
    assert "allows new work" in _limit_check(fresh).message
    assert not stale.passed
    assert "stale" in _limit_check(stale).message
    assert not future.passed
    assert "materially future-dated" in _limit_check(future).message
    assert not invalid.passed
    assert "invalid timestamp" in _limit_check(invalid).message


def test_first_project_setup_rejects_target_project_path_that_does_not_exist(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "data").mkdir()

    result = validate_first_project_setup(
        _settings(project_root, tmp_path / "missing-target"),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "workers.target_project_path" for check in result.failed_checks)


def test_first_project_setup_reports_multi_repo_visibility_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(
        _settings(
            project_root,
            target_project,
            extra={
                "TARGET_IMPLEMENTATION_REPOSITORY": "example-org/ap-airline",
                "DOCUMENTATION_REPOSITORY": "example-org/ap-docs",
                "DOCUMENTATION_JIRA_DEV_PANEL_EXPECTED": "false",
            },
        ),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )
    checklist = format_first_project_setup_validation(result)

    assert result.passed
    assert "repositories.target-implementation" in checklist
    assert "repositories.documentation.jira_development_panel" in checklist
    assert "WARNING: documentation: example-org/ap-docs will require explicit Jira PR links." in checklist


def test_first_project_setup_rejects_invalid_configured_repository_lane(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(
        _settings(
            project_root,
            target_project,
            extra={"TARGET_IMPLEMENTATION_REPOSITORY": "missing-owner"},
        ),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "repositories.target-implementation" for check in result.failed_checks)


def test_first_project_setup_rejects_missing_docker_git_ssh_key_source(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(
        _settings(
            project_root,
            target_project,
            extra={
                "GITHUB_AUTH_MODE": "ssh",
                "GIT_REMOTE_MODE": "ssh",
            },
        ),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "github.ssh_key_source" for check in result.failed_checks)


def test_first_project_setup_rejects_durable_paths_outside_docker_data_mount(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    settings = _settings(
        project_root,
        target_project,
        extra={"DURABLE_PO_INBOX_PATH": str(tmp_path / "outside-data" / "po-inbox")},
    )

    result = validate_first_project_setup(
        settings,
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "paths.po_inbox.docker_visible" for check in result.failed_checks)


def test_first_project_setup_checks_po_inbox_status_directory_writes(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    po_inbox = project_root / "data" / "po-inbox"
    answered = po_inbox / "answered"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()
    answered.mkdir(parents=True)
    answered.chmod(0o555)

    try:
        result = validate_first_project_setup(
            _settings(project_root, target_project),
            project_root=project_root,
            latest_limit_record=_available_limit_record(),
        )
    finally:
        answered.chmod(0o755)

    assert not result.passed
    failed = next(check for check in result.failed_checks if check.name == "paths.po_inbox.answered.writable")
    assert "ownership or container volume permissions" in failed.message


def test_first_project_setup_checks_confluence_space_mirror_writes(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    mirror_root = project_root / "data" / "confluence-mirror"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()
    mirror_root.mkdir()
    (mirror_root / "DEMO").write_text("not a directory", encoding="utf-8")

    result = validate_first_project_setup(
        _settings(project_root, target_project),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "paths.confluence_mirror.DEMO.writable" for check in result.failed_checks)


def test_first_project_setup_rejects_misplaced_target_project_po_inbox(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    (target_project / "data" / "po-inbox").mkdir(parents=True)

    result = validate_first_project_setup(
        _settings(project_root, target_project),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    boundary_checks = [check for check in result.failed_checks if check.name == "po_inbox.platform_boundary"]
    assert boundary_checks
    assert "misplaced PO inbox path" in boundary_checks[0].message


def test_first_project_setup_rejects_platform_inbox_inside_target_project(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()

    result = validate_first_project_setup(
        _settings(
            project_root,
            target_project,
            extra={"DURABLE_PO_INBOX_PATH": str(target_project / "data" / "po-inbox")},
        ),
        project_root=project_root,
        latest_limit_record=_available_limit_record(),
    )

    assert not result.passed
    assert any(check.name == "po_inbox.platform_boundary" for check in result.failed_checks)


def _settings(project_root: Path, target_project: Path, *, extra: dict[str, str] | None = None):
    data_root = project_root / "data"
    values = {
        "GITHUB_TOKEN": "github-token",
        "GITHUB_REPOSITORY": "example-org/example",
        "JIRA_PROJECT_KEY": "DEMO",
        "JIRA_BOARD_ID": "42",
        "JIRA_EMAIL": "po@example.com",
        "JIRA_API_TOKEN": "jira-token",
        "CONFLUENCE_SPACE_KEY": "DEMO",
        "CONFLUENCE_PARENT_PAGE_ID": "123",
        "CONFLUENCE_EMAIL": "po@example.com",
        "CONFLUENCE_API_TOKEN": "confluence-token",
        "AGILETEST_CLIENT_ID": "agiletest-client",
        "AGILETEST_API_TOKEN": "agiletest-token",
        "TARGET_PROJECT_PATH": str(target_project),
        "DURABLE_PO_INBOX_PATH": str(data_root / "po-inbox"),
        "DURABLE_CONTEXT_PACKS_PATH": str(data_root / "context-packs"),
        "DURABLE_CODEX_JOBS_PATH": str(data_root / "codex-jobs"),
        "DURABLE_CODEX_RESULTS_PATH": str(data_root / "codex-results"),
        "DURABLE_CODEX_LIMITS_PATH": str(data_root / "codex-limits"),
        "DURABLE_AGENT_STATE_PATH": str(data_root / "agent-state"),
        "DURABLE_AGENT_LOGS_PATH": str(data_root / "agent-logs"),
        "DURABLE_PO_DECISIONS_PATH": str(data_root / "po-decisions"),
        "DURABLE_SPRINTS_PATH": str(data_root / "sprints"),
        "DURABLE_CONFLUENCE_MIRROR_PATH": str(data_root / "confluence-mirror"),
    }
    if extra:
        values.update(extra)
    return settings_from_mapping(values)


def _available_limit_record():
    return _available_limit_record_at("2026-07-10T12:00:00Z")


def _available_limit_record_at(observed_at: datetime | str):
    if isinstance(observed_at, datetime):
        observed_at = observed_at.isoformat().replace("+00:00", "Z")
    return build_codex_limit_availability_record(
        record_id="available-20260710T120000Z",
        short_window=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=99,
            reset_at="2026-07-10T17:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
        ),
        broad_quota=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-17T12:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
        ),
    )


def _limit_check(result):
    return next(check for check in result.checks if check.name == "codex_limits.latest")
