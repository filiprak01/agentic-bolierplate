from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain import (
    IntegrationReadinessCheck,
    IntegrationReadinessName,
    IntegrationReadinessStatus,
    build_integration_readiness_report,
    format_integration_readiness_report,
    integration_readiness_report_to_dict,
)
from agentic_boilerplate.integrations import (
    GitHubAdapterError,
    GitHubBranchMetadata,
    GitHubRepositoryConfiguration,
    GitHubRepositoryMetadata,
)
import agentic_boilerplate.integrations.live_readiness as live_readiness_module
from agentic_boilerplate.integrations.live_readiness import (
    LiveIntegrationReadinessOptions,
    build_live_integration_readiness_report,
    _github_checks,
    _required_names_check,
)


def test_integration_readiness_redacts_secret_values() -> None:
    report = build_integration_readiness_report(
        (
            IntegrationReadinessCheck(
                integration=IntegrationReadinessName.GITHUB,
                name="repository_access",
                status=IntegrationReadinessStatus.FAIL,
                message="GitHub token=github_pat_secretValue failed with Bearer ghp_secretValue",
                remediation="Set api_token=jira-secret",
            ),
        )
    )

    rendered = format_integration_readiness_report(report)
    payload = integration_readiness_report_to_dict(report)

    assert report.assignment_allowed is False
    assert "***REDACTED***" in rendered
    assert "github_pat_secretValue" not in rendered
    assert "ghp_secretValue" not in str(payload)
    assert "jira-secret" not in str(payload)


def test_live_integration_readiness_allows_assignment_with_required_config_and_skipped_network(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "platform"
    target_project = tmp_path / "target"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()
    (target_project / ".git").mkdir()

    report = build_live_integration_readiness_report(
        _settings(target_project),
        LiveIntegrationReadinessOptions(project_root=project_root, skip_network=True),
    )

    assert report.assignment_allowed is True
    statuses = {check.status for check in report.checks}
    assert IntegrationReadinessStatus.WARNING in statuses
    assert IntegrationReadinessStatus.FAIL not in statuses
    assert any(check.integration == IntegrationReadinessName.FIGMA for check in report.checks)


def test_live_integration_readiness_blocks_missing_required_configuration(tmp_path: Path) -> None:
    project_root = tmp_path / "platform"
    project_root.mkdir()

    report = build_live_integration_readiness_report(
        settings_from_mapping({}),
        LiveIntegrationReadinessOptions(project_root=project_root, skip_network=True),
    )

    assert report.assignment_allowed is False
    blocking = {check.integration for check in report.blocking_checks}
    assert IntegrationReadinessName.TARGET_REPOSITORY in blocking
    assert IntegrationReadinessName.GITHUB in blocking
    assert IntegrationReadinessName.AGILETEST in blocking


class _GitHubAdapterStub:
    def __init__(self, repository: GitHubRepositoryMetadata | None = None, error: Exception | None = None) -> None:
        self.repository = repository
        self.error = error

    def validate_access(self) -> GitHubRepositoryConfiguration:
        if self.error is not None:
            raise self.error
        assert self.repository is not None
        return GitHubRepositoryConfiguration(
            repository=self.repository,
            default_branch=GitHubBranchMetadata(name="main", sha="a" * 40),
        )


def test_github_live_readiness_blocks_readable_repo_without_write_permission(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target"
    target_project.mkdir()
    repository = GitHubRepositoryMetadata(
        full_name="example-org/example",
        default_branch="main",
        private=True,
        permissions={"pull": True, "push": False, "maintain": False, "admin": False},
        role_name="read",
    )
    monkeypatch.setattr(
        live_readiness_module,
        "_github_adapter",
        lambda settings, timeout_seconds: _GitHubAdapterStub(repository=repository),
    )

    report = build_integration_readiness_report(
        tuple(
            _github_checks(
                _settings(target_project),
                LiveIntegrationReadinessOptions(timeout_seconds=1),
            )
        )
    )

    write_check = next(check for check in report.checks if check.name == "write_permission")
    assert write_check.status == IntegrationReadinessStatus.FAIL
    assert write_check.blocking is True
    assert "organization access" in write_check.remediation
    assert report.assignment_allowed is False


def test_github_live_readiness_redacts_private_repo_access_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target"
    target_project.mkdir()
    monkeypatch.setattr(
        live_readiness_module,
        "_github_adapter",
        lambda settings, timeout_seconds: _GitHubAdapterStub(
            error=GitHubAdapterError("HTTP 403 token=github_pat_secretValue")
        ),
    )

    report = build_integration_readiness_report(
        tuple(
            _github_checks(
                _settings(target_project),
                LiveIntegrationReadinessOptions(timeout_seconds=1),
            )
        )
    )
    rendered = format_integration_readiness_report(report)

    assert report.assignment_allowed is False
    assert "***REDACTED***" in rendered
    assert "github_pat_secretValue" not in rendered


def test_github_live_readiness_checks_local_git_read_and_dry_run_push(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target"
    target_project.mkdir()
    (target_project / ".git").mkdir()
    repository = GitHubRepositoryMetadata(
        full_name="example-org/example",
        default_branch="main",
        private=True,
        permissions={"pull": True, "push": True},
        role_name="write",
    )
    calls = []

    def fake_git(args, timeout_seconds):
        calls.append(args)
        return live_readiness_module._LocalGitCommandResult(
            0,
            stdout="https://github.com/example-org/example.git\n",
        )

    monkeypatch.setattr(
        live_readiness_module,
        "_github_adapter",
        lambda settings, timeout_seconds: _GitHubAdapterStub(repository=repository),
    )
    monkeypatch.setattr(live_readiness_module, "_run_git_command", fake_git)

    report = build_integration_readiness_report(
        tuple(
            _github_checks(
                _settings(target_project),
                LiveIntegrationReadinessOptions(timeout_seconds=1),
            )
        )
    )

    statuses = {check.name: check.status for check in report.checks}
    assert statuses["local_git_remote"] == IntegrationReadinessStatus.PASS
    assert statuses["local_git_read"] == IntegrationReadinessStatus.PASS
    assert statuses["local_git_write"] == IntegrationReadinessStatus.PASS
    assert any("ls-remote" in args for args in calls)
    assert any("push" in args and "--dry-run" in args for args in calls)


def test_github_live_readiness_redacts_local_git_failure_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target"
    target_project.mkdir()
    (target_project / ".git").mkdir()
    repository = GitHubRepositoryMetadata(
        full_name="example-org/example",
        default_branch="main",
        private=True,
        permissions={"pull": True, "push": True},
        role_name="write",
    )

    def fake_git(args, timeout_seconds):
        if "ls-remote" in args:
            return live_readiness_module._LocalGitCommandResult(
                128,
                stderr="remote: token=github_pat_secretValue denied",
            )
        return live_readiness_module._LocalGitCommandResult(
            0,
            stdout="https://github.com/example-org/example.git\n",
        )

    monkeypatch.setattr(
        live_readiness_module,
        "_github_adapter",
        lambda settings, timeout_seconds: _GitHubAdapterStub(repository=repository),
    )
    monkeypatch.setattr(live_readiness_module, "_run_git_command", fake_git)

    report = build_integration_readiness_report(
        tuple(
            _github_checks(
                _settings(target_project),
                LiveIntegrationReadinessOptions(timeout_seconds=1),
            )
        )
    )
    rendered = format_integration_readiness_report(report)

    assert report.assignment_allowed is False
    assert "local_git_read" in rendered
    assert "***REDACTED***" in rendered
    assert "github_pat_secretValue" not in rendered


def test_required_names_check_matches_jira_names_case_insensitively() -> None:
    check = _required_names_check(
        IntegrationReadinessName.JIRA,
        "workflow_statuses",
        ("IN PROGRESS", "ACCEPTED/DONE"),
        {"In Progress", "Accepted/Done"},
        "Required Jira workflow statuses are available.",
        "Fix statuses.",
    )

    assert check.status == IntegrationReadinessStatus.PASS


def _settings(target_project: Path):
    return settings_from_mapping(
        {
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
        }
    )
