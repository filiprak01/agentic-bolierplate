"""Non-mutating live readiness probes for configured integrations."""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.config import PlatformSettings
from agentic_boilerplate.domain.integration_readiness import (
    IntegrationReadinessCheck,
    IntegrationReadinessName,
    IntegrationReadinessReport,
    IntegrationReadinessStatus,
    build_integration_readiness_report,
    redact_integration_readiness_text,
)
from agentic_boilerplate.integrations.confluence import (
    ConfluenceAdapterError,
    ConfluenceAdapterConfig,
    ConfluenceCloudDocumentationAdapter,
    ConfluenceCloudTransport,
)
from agentic_boilerplate.integrations.github import (
    GitHubAdapterError,
    GitHubRestRepositoryAdapter,
    GitHubRestTransport,
    github_config_from_settings,
)
from agentic_boilerplate.integrations.jira import (
    JiraAdapterConfig,
    JiraAdapterError,
    JiraCloudProjectIssueAdapter,
    JiraCloudTransport,
)


REQUIRED_JIRA_STATUSES = (
    "FUNNEL",
    "READY TO START",
    "IN PROGRESS",
    "DEV COMPLETED",
    "IN TESTING",
    "TEST COMPLETED",
    "ACCEPTED/DONE",
)
REQUIRED_JIRA_ISSUE_TYPES = ("Epic", "Story", "Task", "Bug", "Subtask", "Test")
REQUIRED_JIRA_LINK_TYPES = ("Blocks",)


@dataclass(frozen=True)
class LiveIntegrationReadinessOptions:
    """Operator options for readiness probes."""

    project_root: Path | str = "."
    sample_issue_key: str = ""
    skip_network: bool = False
    timeout_seconds: int = 15


def build_live_integration_readiness_report(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> IntegrationReadinessReport:
    """Build a non-mutating readiness report for configured integrations."""

    checks: list[IntegrationReadinessCheck] = []
    checks.extend(_target_repository_checks(settings, options))
    checks.extend(_github_checks(settings, options))
    checks.extend(_jira_checks(settings, options))
    checks.extend(_confluence_checks(settings, options))
    checks.extend(_agiletest_checks(settings))
    checks.extend(_figma_checks(settings, options))
    return build_integration_readiness_report(tuple(checks))


def _target_repository_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    target_path = settings.workers.target_project_path.strip()
    if not target_path:
        return (
            _check(
                IntegrationReadinessName.TARGET_REPOSITORY,
                "path_configured",
                IntegrationReadinessStatus.FAIL,
                "TARGET_PROJECT_PATH is not configured.",
                "Set TARGET_PROJECT_PATH to the local target project root before assigning workers.",
            ),
        )
    target = Path(target_path).expanduser()
    project_root = Path(options.project_root).resolve()
    data_root = project_root / "data"
    return (
        _check(
            IntegrationReadinessName.TARGET_REPOSITORY,
            "path_exists",
            IntegrationReadinessStatus.PASS if target.is_dir() else IntegrationReadinessStatus.FAIL,
            "Target project path exists." if target.is_dir() else "TARGET_PROJECT_PATH does not exist.",
            "" if target.is_dir() else "Create or clone the target project repository at TARGET_PROJECT_PATH.",
        ),
        _check(
            IntegrationReadinessName.TARGET_REPOSITORY,
            "git_repository",
            IntegrationReadinessStatus.PASS if (target / ".git").exists() else IntegrationReadinessStatus.WARNING,
            "Target project has Git metadata."
            if (target / ".git").exists()
            else "Target project path is not a Git worktree, or Git metadata is not visible.",
            "" if (target / ".git").exists() else "Use a Git worktree or document why the target project is local-only.",
        ),
        _check(
            IntegrationReadinessName.TARGET_REPOSITORY,
            "durable_data_boundary",
            IntegrationReadinessStatus.PASS if data_root.exists() else IntegrationReadinessStatus.FAIL,
            "Platform durable data root exists under the boilerplate project."
            if data_root.exists()
            else "Platform durable data root is missing.",
            "" if data_root.exists() else "Create the platform data directory before starting workers.",
        ),
    )


def _github_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    if not _owner_repo(settings.github.repository):
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "repository_configured",
                IntegrationReadinessStatus.FAIL,
                "GITHUB_REPOSITORY must use owner/name format.",
                "Set GITHUB_REPOSITORY for the target repository.",
            ),
        )
    if not settings.github.token:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "token_configured",
                IntegrationReadinessStatus.FAIL,
                "GitHub token is missing.",
                "Set GITHUB_TOKEN or GH_TOKEN with repository read/write and PR permissions.",
            ),
        )
    if options.skip_network:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "live_probe",
                IntegrationReadinessStatus.WARNING,
                "GitHub live probe skipped by operator option.",
                "Run without --skip-network before enabling detached worker assignment.",
            ),
        )
    try:
        configuration = _github_adapter(settings, options.timeout_seconds).validate_access()
    except GitHubAdapterError as exc:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "repository_access",
                IntegrationReadinessStatus.FAIL,
                f"GitHub repository access failed: {exc}",
                "Check token scopes, organization access, and GITHUB_REPOSITORY.",
            ),
        )
    checks: list[IntegrationReadinessCheck] = [
        _check(
            IntegrationReadinessName.GITHUB,
            "repository_access",
            IntegrationReadinessStatus.PASS,
            f"Repository {configuration.repository.full_name} is readable.",
        ),
        _check(
            IntegrationReadinessName.GITHUB,
            "default_branch",
            IntegrationReadinessStatus.PASS
            if configuration.default_branch.name == configuration.repository.default_branch
            else IntegrationReadinessStatus.WARNING,
            f"Default branch {configuration.repository.default_branch} is readable.",
            "Confirm GITHUB_DEFAULT_BRANCH if this is not the intended integration branch.",
        ),
        _check(
            IntegrationReadinessName.GITHUB,
            "write_permission",
            IntegrationReadinessStatus.PASS
            if configuration.repository.has_write_permission
            else IntegrationReadinessStatus.FAIL,
            "Repository write permission is available from GitHub metadata."
            if configuration.repository.has_write_permission
            else "Repository is readable, but GitHub metadata does not report branch write permission.",
            ""
            if configuration.repository.has_write_permission
            else (
                "Refresh GitHub CLI or PAT credentials with repository contents write access and organization access, "
                "run gh auth setup-git, then rerun setup live-diagnostic."
            ),
        ),
    ]
    checks.extend(_local_git_identity_checks(settings, options))
    return tuple(checks)


@dataclass(frozen=True)
class _LocalGitCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _local_git_identity_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    target_path = settings.workers.target_project_path.strip()
    if not target_path:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_checkout",
                IntegrationReadinessStatus.FAIL,
                "TARGET_PROJECT_PATH is required before validating local Git identity.",
                "Set TARGET_PROJECT_PATH to the target repository checkout and rerun setup live-diagnostic.",
            ),
        )

    target = Path(target_path).expanduser()
    if not (target / ".git").exists():
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_checkout",
                IntegrationReadinessStatus.FAIL,
                "TARGET_PROJECT_PATH is not a Git checkout visible to setup validation.",
                "Clone the target repository or fix TARGET_PROJECT_PATH before assigning GitHub-backed work.",
            ),
        )

    remote = _run_git_command(("git", "-C", str(target), "remote", "get-url", "origin"), options.timeout_seconds)
    if remote.returncode != 0:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_remote",
                IntegrationReadinessStatus.FAIL,
                "Local Git origin remote is not readable: " + _git_failure_summary(remote),
                "Configure the origin remote for the target repository and rerun setup live-diagnostic.",
            ),
        )

    remote_url = remote.stdout.strip()
    if settings.github.repository and settings.github.repository.lower() not in remote_url.lower():
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_remote",
                IntegrationReadinessStatus.FAIL,
                "Local Git origin remote does not match GITHUB_REPOSITORY.",
                "Point origin at the configured repository or update GITHUB_REPOSITORY before assigning workers.",
            ),
        )

    read = _run_git_command(("git", "-C", str(target), "ls-remote", "--exit-code", "origin", "HEAD"), options.timeout_seconds)
    if read.returncode != 0:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_read",
                IntegrationReadinessStatus.FAIL,
                "Local Git identity cannot read origin HEAD: " + _git_failure_summary(read),
                "Refresh Git credentials, run gh auth setup-git or configure token auth, then rerun setup live-diagnostic.",
            ),
        )

    probe_branch = _git_preflight_branch_name(settings.github.repository)
    write = _run_git_command(
        (
            "git",
            "-C",
            str(target),
            "push",
            "--dry-run",
            "origin",
            f"HEAD:refs/heads/{probe_branch}",
        ),
        options.timeout_seconds,
    )
    if write.returncode != 0:
        return (
            _check(
                IntegrationReadinessName.GITHUB,
                "local_git_write",
                IntegrationReadinessStatus.FAIL,
                "Local Git identity cannot push a dry-run preflight branch: " + _git_failure_summary(write),
                "Refresh Git credentials, verify organization access and branch permissions, then rerun setup live-diagnostic.",
            ),
        )

    return (
        _check(
            IntegrationReadinessName.GITHUB,
            "local_git_remote",
            IntegrationReadinessStatus.PASS,
            "Local Git origin remote matches the configured repository.",
        ),
        _check(
            IntegrationReadinessName.GITHUB,
            "local_git_read",
            IntegrationReadinessStatus.PASS,
            "Local Git identity can read origin HEAD.",
        ),
        _check(
            IntegrationReadinessName.GITHUB,
            "local_git_write",
            IntegrationReadinessStatus.PASS,
            "Local Git identity can dry-run push a preflight branch.",
        ),
    )


def _run_git_command(args: tuple[str, ...], timeout_seconds: int) -> _LocalGitCommandResult:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return _LocalGitCommandResult(127, stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return _LocalGitCommandResult(124, stdout=exc.stdout or "", stderr=exc.stderr or "Git command timed out.")
    return _LocalGitCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _git_failure_summary(result: _LocalGitCommandResult) -> str:
    details = (result.stderr or result.stdout or "no output").strip()
    return redact_integration_readiness_text(details)[:240]


def _git_preflight_branch_name(repository: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in repository)
    slug = "-".join(part for part in slug.split("-") if part)
    if not slug:
        slug = "repository"
    return f"agentic-preflight/{slug}-write-check"


def _jira_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    missing = [
        name
        for name, value in (
            ("JIRA_BASE_URL", settings.jira.base_url),
            ("JIRA_PROJECT_KEY", settings.jira.project_key),
            ("JIRA_BOARD_ID", settings.jira.board_id),
            ("JIRA_EMAIL", settings.jira.email),
            ("JIRA_API_TOKEN", settings.jira.api_token),
        )
        if not str(value).strip()
    ]
    if missing:
        return (
            _check(
                IntegrationReadinessName.JIRA,
                "configuration",
                IntegrationReadinessStatus.FAIL,
                "Missing Jira configuration: " + ", ".join(missing),
                "Set the missing Jira values before assigning workers.",
            ),
        )
    if options.skip_network:
        return (
            _check(
                IntegrationReadinessName.JIRA,
                "live_probe",
                IntegrationReadinessStatus.WARNING,
                "Jira live probe skipped by operator option.",
                "Run without --skip-network before enabling detached worker assignment.",
            ),
        )
    try:
        adapter = _jira_adapter(settings, options.timeout_seconds)
        configuration = adapter.validate_access()
    except JiraAdapterError as exc:
        return (
            _check(
                IntegrationReadinessName.JIRA,
                "project_board_access",
                IntegrationReadinessStatus.FAIL,
                f"Jira project or board access failed: {exc}",
                "Check Jira token, project key, board id, and board/project alignment.",
            ),
        )

    status_names = {status.name for status in configuration.statuses}
    issue_type_names = {issue_type.name for issue_type in configuration.issue_types}
    link_type_names = {link_type.name for link_type in configuration.link_types}
    checks: list[IntegrationReadinessCheck] = [
        _check(
            IntegrationReadinessName.JIRA,
            "project_board_access",
            IntegrationReadinessStatus.PASS,
            f"Project {configuration.project.key} and board {configuration.board.id} are readable.",
        ),
        _required_names_check(
            IntegrationReadinessName.JIRA,
            "workflow_statuses",
            REQUIRED_JIRA_STATUSES,
            status_names,
            "Required Jira workflow statuses are available.",
            "Add or rename Jira statuses to match the configured workflow.",
        ),
        _required_names_check(
            IntegrationReadinessName.JIRA,
            "issue_types",
            REQUIRED_JIRA_ISSUE_TYPES,
            issue_type_names,
            "Required Jira issue types are available.",
            "Add missing issue types or update the process configuration.",
        ),
        _required_names_check(
            IntegrationReadinessName.JIRA,
            "link_types",
            REQUIRED_JIRA_LINK_TYPES,
            link_type_names,
            "Required Jira dependency link types are available.",
            "Enable the Blocks link type or update dependency link configuration.",
        ),
    ]
    try:
        sprints = adapter.list_sprints()
        checks.append(
            _check(
                IntegrationReadinessName.JIRA,
                "sprint_access",
                IntegrationReadinessStatus.PASS if sprints else IntegrationReadinessStatus.WARNING,
                f"Board sprint endpoint is readable and returned {len(sprints)} sprint(s).",
                "Create or expose at least one Scrum sprint if sprint planning is required." if not sprints else "",
            )
        )
    except JiraAdapterError as exc:
        checks.append(
            _check(
                IntegrationReadinessName.JIRA,
                "sprint_access",
                IntegrationReadinessStatus.FAIL,
                f"Jira sprint access failed: {exc}",
                "Check board id, Jira Agile API access, and Scrum board permissions.",
            )
        )
    if options.sample_issue_key:
        try:
            transitions = adapter.get_transitions(options.sample_issue_key)
            checks.append(
                _check(
                    IntegrationReadinessName.JIRA,
                    "sample_issue_transitions",
                    IntegrationReadinessStatus.PASS if transitions else IntegrationReadinessStatus.WARNING,
                    f"Sample issue {options.sample_issue_key} has {len(transitions)} available transitions.",
                    "Confirm the sample issue is in an actionable status." if not transitions else "",
                )
            )
        except JiraAdapterError as exc:
            checks.append(
                _check(
                    IntegrationReadinessName.JIRA,
                    "sample_issue_transitions",
                    IntegrationReadinessStatus.WARNING,
                    f"Sample issue transition probe failed: {exc}",
                    "Provide a visible sample issue key or omit this optional check.",
                )
            )
    else:
        checks.append(
            _check(
                IntegrationReadinessName.JIRA,
                "sample_issue_transitions",
                IntegrationReadinessStatus.WARNING,
                "No sample issue key was provided, so transition availability was not probed.",
                "Pass --sample-issue-key with a non-critical Jira issue when validating transitions.",
            )
        )
    return tuple(checks)


def _confluence_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    missing = [
        name
        for name, value in (
            ("CONFLUENCE_BASE_URL", settings.confluence.base_url),
            ("CONFLUENCE_SPACE_KEY", settings.confluence.space_key),
            ("CONFLUENCE_PARENT_PAGE_ID", settings.confluence.parent_page_id),
            ("CONFLUENCE_EMAIL", settings.confluence.email),
            ("CONFLUENCE_API_TOKEN", settings.confluence.api_token),
        )
        if not str(value).strip()
    ]
    if missing:
        return (
            _check(
                IntegrationReadinessName.CONFLUENCE,
                "configuration",
                IntegrationReadinessStatus.FAIL,
                "Missing Confluence configuration: " + ", ".join(missing),
                "Set the missing Confluence values or configure the GitHub Pages documentation alternative.",
            ),
        )
    if options.skip_network:
        return (
            _check(
                IntegrationReadinessName.CONFLUENCE,
                "live_probe",
                IntegrationReadinessStatus.WARNING,
                "Confluence live probe skipped by operator option.",
                "Run without --skip-network before enabling documentation publication workers.",
            ),
        )
    try:
        configuration = _confluence_adapter(settings, options.timeout_seconds).validate_access()
    except ConfluenceAdapterError as exc:
        return (
            _check(
                IntegrationReadinessName.CONFLUENCE,
                "space_parent_access",
                IntegrationReadinessStatus.FAIL,
                f"Confluence space or parent page access failed: {exc}",
                "Check Confluence token, space key, parent page id, and account permissions.",
            ),
        )
    return (
        _check(
            IntegrationReadinessName.CONFLUENCE,
            "space_parent_access",
            IntegrationReadinessStatus.PASS,
            f"Space {configuration.space.key} and parent page {configuration.parent_page.id} are readable.",
        ),
    )


def _agiletest_checks(settings: PlatformSettings) -> tuple[IntegrationReadinessCheck, ...]:
    checks: list[IntegrationReadinessCheck] = []
    checks.append(
        _check(
            IntegrationReadinessName.AGILETEST,
            "client_id",
            IntegrationReadinessStatus.PASS if settings.agiletest.client_id else IntegrationReadinessStatus.FAIL,
            "AgileTest client id is configured." if settings.agiletest.client_id else "AgileTest client id is missing.",
            "" if settings.agiletest.client_id else "Set AGILETEST_CLIENT_ID.",
        )
    )
    checks.append(
        _check(
            IntegrationReadinessName.AGILETEST,
            "api_token",
            IntegrationReadinessStatus.PASS if settings.agiletest.api_token else IntegrationReadinessStatus.FAIL,
            "AgileTest token is configured." if settings.agiletest.api_token else "AgileTest token is missing.",
            "" if settings.agiletest.api_token else "Set AGILETEST_API_TOKEN.",
        )
    )
    checks.append(
        _check(
            IntegrationReadinessName.AGILETEST,
            "jira_test_issue_contract",
            IntegrationReadinessStatus.PASS,
            "AgileTest is validated through Jira Test issue visibility and linked evidence workflows.",
        )
    )
    return tuple(checks)


def _figma_checks(
    settings: PlatformSettings,
    options: LiveIntegrationReadinessOptions,
) -> tuple[IntegrationReadinessCheck, ...]:
    token = settings.figma.token.strip()
    file_key = settings.figma.file_key.strip()
    project_url = settings.figma.project_url.strip()
    if not token and not file_key and not project_url:
        return (
            _check(
                IntegrationReadinessName.FIGMA,
                "optional_configuration",
                IntegrationReadinessStatus.SKIPPED,
                "Figma is not configured and will be skipped for non-UI work.",
                "Set FIGMA_TOKEN and FIGMA_FILE_KEY when UI/UX design work requires Figma access.",
            ),
        )
    if bool(token) != bool(file_key):
        return (
            _check(
                IntegrationReadinessName.FIGMA,
                "configuration",
                IntegrationReadinessStatus.WARNING,
                "Figma is partially configured.",
                "Set both FIGMA_TOKEN and FIGMA_FILE_KEY, or leave all Figma fields empty.",
            ),
        )
    if options.skip_network:
        return (
            _check(
                IntegrationReadinessName.FIGMA,
                "live_probe",
                IntegrationReadinessStatus.WARNING,
                "Figma live probe skipped by operator option.",
                "Run without --skip-network before starting UI/UX workers that need Figma.",
            ),
        )
    try:
        _read_figma_file(token=token, file_key=file_key, timeout_seconds=options.timeout_seconds)
    except OSError as exc:
        return (
            _check(
                IntegrationReadinessName.FIGMA,
                "file_access",
                IntegrationReadinessStatus.WARNING,
                f"Figma file access probe failed: {exc}",
                "Check FIGMA_TOKEN, FIGMA_FILE_KEY, and file permissions before UI/UX work starts.",
            ),
        )
    return (
        _check(
            IntegrationReadinessName.FIGMA,
            "file_access",
            IntegrationReadinessStatus.PASS,
            "Figma file is readable.",
        ),
    )


def _read_figma_file(*, token: str, file_key: str, timeout_seconds: int) -> None:
    request = urllib.request.Request(
        "https://api.figma.com/v1/files/" + urllib.parse.quote(file_key, safe="") + "?depth=1",
        headers={"X-Figma-Token": token, "User-Agent": "agentic-boilerplate"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read(1024)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OSError(f"HTTP {exc.code} {redact_integration_readiness_text(body)}") from exc
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from exc


def _required_names_check(
    integration: IntegrationReadinessName,
    name: str,
    required: tuple[str, ...],
    actual: set[str],
    pass_message: str,
    remediation: str,
) -> IntegrationReadinessCheck:
    actual_normalized = {_normalize_name(item) for item in actual}
    missing = tuple(item for item in required if _normalize_name(item) not in actual_normalized)
    return _check(
        integration,
        name,
        IntegrationReadinessStatus.PASS if not missing else IntegrationReadinessStatus.FAIL,
        pass_message if not missing else "Missing required values: " + ", ".join(missing),
        "" if not missing else remediation,
    )


def _check(
    integration: IntegrationReadinessName,
    name: str,
    status: IntegrationReadinessStatus,
    message: str,
    remediation: str = "",
) -> IntegrationReadinessCheck:
    return IntegrationReadinessCheck(
        integration=integration,
        name=name,
        status=status,
        message=message,
        remediation=remediation,
    )


def _owner_repo(repository: str) -> bool:
    parts = tuple(part.strip() for part in repository.split("/", maxsplit=1))
    return len(parts) == 2 and all(parts)


def _normalize_name(value: str) -> str:
    return " ".join(value.replace("/", " / ").split()).casefold()


def _github_adapter(settings: PlatformSettings, timeout_seconds: int) -> GitHubRestRepositoryAdapter:
    config = github_config_from_settings(settings)
    return GitHubRestRepositoryAdapter(
        config,
        transport=GitHubRestTransport(config, timeout_seconds=timeout_seconds),
    )


def _jira_adapter(settings: PlatformSettings, timeout_seconds: int) -> JiraCloudProjectIssueAdapter:
    config = JiraAdapterConfig(
        base_url=settings.jira.base_url,
        project_key=settings.jira.project_key,
        board_id=settings.jira.board_id,
        email=settings.jira.email,
        api_token=settings.jira.api_token,
    )
    return JiraCloudProjectIssueAdapter(
        config,
        transport=JiraCloudTransport(config, timeout_seconds=timeout_seconds),
    )


def _confluence_adapter(settings: PlatformSettings, timeout_seconds: int) -> ConfluenceCloudDocumentationAdapter:
    config = ConfluenceAdapterConfig(
        base_url=settings.confluence.base_url,
        space_key=settings.confluence.space_key,
        parent_page_id=settings.confluence.parent_page_id,
        email=settings.confluence.email,
        api_token=settings.confluence.api_token,
    )
    return ConfluenceCloudDocumentationAdapter(
        config,
        transport=ConfluenceCloudTransport(config, timeout_seconds=timeout_seconds),
    )
