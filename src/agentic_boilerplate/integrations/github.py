"""Configurable GitHub integration boundary."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol


class GitHubAdapterError(RuntimeError):
    """Raised when GitHub adapter operations fail."""


class GitHubTransport(Protocol):
    """HTTP transport used by the GitHub REST adapter."""

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Send one GitHub request and return a decoded JSON object."""


@dataclass(frozen=True)
class GitHubAdapterConfig:
    """Configuration for one target GitHub repository."""

    repository: str
    token: str = ""
    default_branch: str = "main"
    api_base_url: str = "https://api.github.com"

    @property
    def normalized_api_base_url(self) -> str:
        return self.api_base_url.rstrip("/")

    @property
    def owner(self) -> str:
        return self._repository_parts()[0]

    @property
    def name(self) -> str:
        return self._repository_parts()[1]

    def _repository_parts(self) -> tuple[str, str]:
        parts = tuple(part.strip() for part in self.repository.split("/", maxsplit=1))
        if len(parts) != 2 or not all(parts):
            raise GitHubAdapterError(
                "GitHub repository must use owner/name format."
            )
        return parts


@dataclass(frozen=True)
class GitHubRepositoryMetadata:
    full_name: str
    default_branch: str
    private: bool = False
    html_url: str = ""
    clone_url: str = ""
    ssh_url: str = ""
    permissions: Mapping[str, bool] | None = None
    role_name: str = ""

    @property
    def has_write_permission(self) -> bool:
        permissions = self.permissions or {}
        role_name = self.role_name.strip().lower()
        return bool(
            permissions.get("admin")
            or permissions.get("maintain")
            or permissions.get("push")
            or role_name in {"admin", "maintain", "write"}
        )


@dataclass(frozen=True)
class GitHubBranchMetadata:
    name: str
    sha: str
    protected: bool = False


@dataclass(frozen=True)
class GitHubPullRequestFields:
    title: str
    head: str
    base: str
    body: str = ""
    draft: bool = False
    maintainer_can_modify: bool = True


@dataclass(frozen=True)
class GitHubPullRequestMetadata:
    number: int
    title: str
    head: str
    base: str
    state: str
    draft: bool = False
    html_url: str = ""
    mergeable_state: str = ""
    head_sha: str = ""


@dataclass(frozen=True)
class GitHubPullRequestMergeFields:
    number: int
    commit_title: str
    commit_message: str = ""
    merge_method: str = "merge"


@dataclass(frozen=True)
class GitHubPullRequestMergeResult:
    number: int
    merged: bool
    sha: str
    message: str = ""


@dataclass(frozen=True)
class GitHubCheckRun:
    name: str
    status: str
    conclusion: str = ""
    details_url: str = ""


@dataclass(frozen=True)
class GitHubPullRequestChecks:
    pull_request_number: int
    head_sha: str
    runs: tuple[GitHubCheckRun, ...] = ()

    @property
    def has_failures(self) -> bool:
        return any(run.conclusion in {"failure", "cancelled", "timed_out"} for run in self.runs)

    @property
    def is_complete(self) -> bool:
        return bool(self.runs) and all(run.status == "completed" for run in self.runs)


@dataclass(frozen=True)
class GitHubRepositoryConfiguration:
    repository: GitHubRepositoryMetadata
    default_branch: GitHubBranchMetadata


class GitHubRepositoryAdapter(Protocol):
    """Configurable GitHub repository adapter contract."""

    config: GitHubAdapterConfig

    def validate_access(self) -> GitHubRepositoryConfiguration:
        """Read repository metadata and fail when access is not valid."""

    def get_repository(self) -> GitHubRepositoryMetadata:
        """Read metadata for the configured repository."""

    def get_branch(self, branch_name: str) -> GitHubBranchMetadata:
        """Read metadata for one branch."""

    def create_branch(self, branch_name: str, from_ref: str) -> GitHubBranchMetadata:
        """Create a branch from an existing branch, tag, or commit SHA."""

    def create_pull_request(self, fields: GitHubPullRequestFields) -> GitHubPullRequestMetadata:
        """Open a pull request in the configured repository."""

    def get_pull_request(self, number: int) -> GitHubPullRequestMetadata:
        """Read pull request state."""

    def get_pull_request_checks(self, number: int) -> GitHubPullRequestChecks:
        """Read pull request check placeholders or check-run state."""

    def merge_pull_request(self, fields: GitHubPullRequestMergeFields) -> GitHubPullRequestMergeResult:
        """Merge a pull request after review approval."""


class GitHubRestTransport:
    """Small urllib-based GitHub REST transport."""

    def __init__(self, config: GitHubAdapterConfig, *, timeout_seconds: int = 45) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.config.normalized_api_base_url + path,
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            message = _github_error_message(raw)
            raise GitHubAdapterError(f"GitHub request failed: HTTP {exc.code} {message}") from exc
        except urllib.error.URLError as exc:
            raise GitHubAdapterError(f"GitHub request failed: {exc.reason}") from exc

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "agentic-boilerplate",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers


class GitHubRestRepositoryAdapter:
    """GitHub REST implementation for one configured repository."""

    def __init__(
        self,
        config: GitHubAdapterConfig,
        *,
        transport: GitHubTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or GitHubRestTransport(config)

    def validate_access(self) -> GitHubRepositoryConfiguration:
        repository = self.get_repository()
        default_branch = self.get_branch(repository.default_branch or self.config.default_branch)
        return GitHubRepositoryConfiguration(
            repository=repository,
            default_branch=default_branch,
        )

    def get_repository(self) -> GitHubRepositoryMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                _repo_path(self.config),
            )
        )
        return _repository_from_json(response, self.config)

    def get_branch(self, branch_name: str) -> GitHubBranchMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                _repo_path(self.config) + "/branches/" + urllib.parse.quote(branch_name, safe=""),
            )
        )
        return _branch_from_json(response, fallback_name=branch_name)

    def create_branch(self, branch_name: str, from_ref: str) -> GitHubBranchMetadata:
        source_sha = from_ref if _looks_like_sha(from_ref) else self.get_branch(_branch_name_from_ref(from_ref)).sha
        payload = {
            "ref": f"refs/heads/{branch_name}",
            "sha": source_sha,
        }
        response = _dict(
            self._transport.request(
                "POST",
                _repo_path(self.config) + "/git/refs",
                payload,
            )
        )
        return GitHubBranchMetadata(
            name=branch_name,
            sha=str(_dict(response.get("object")).get("sha") or source_sha),
        )

    def create_pull_request(self, fields: GitHubPullRequestFields) -> GitHubPullRequestMetadata:
        payload = {
            "title": fields.title,
            "head": fields.head,
            "base": fields.base,
            "body": fields.body,
            "draft": fields.draft,
            "maintainer_can_modify": fields.maintainer_can_modify,
        }
        response = _dict(
            self._transport.request(
                "POST",
                _repo_path(self.config) + "/pulls",
                payload,
            )
        )
        return _pull_request_from_json(response)

    def get_pull_request(self, number: int) -> GitHubPullRequestMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                _repo_path(self.config) + f"/pulls/{number}",
            )
        )
        return _pull_request_from_json(response)

    def get_pull_request_checks(self, number: int) -> GitHubPullRequestChecks:
        pull_request = self.get_pull_request(number)
        if not pull_request.head_sha:
            return GitHubPullRequestChecks(pull_request_number=number, head_sha="")
        response = _dict(
            self._transport.request(
                "GET",
                _repo_path(self.config)
                + "/commits/"
                + urllib.parse.quote(pull_request.head_sha, safe="")
                + "/check-runs",
            )
        )
        return GitHubPullRequestChecks(
            pull_request_number=number,
            head_sha=pull_request.head_sha,
            runs=tuple(_check_run_from_json(item) for item in _list(response.get("check_runs"))),
        )

    def merge_pull_request(self, fields: GitHubPullRequestMergeFields) -> GitHubPullRequestMergeResult:
        payload = {
            "commit_title": fields.commit_title,
            "commit_message": fields.commit_message,
            "merge_method": fields.merge_method,
        }
        response = _dict(
            self._transport.request(
                "PUT",
                _repo_path(self.config) + f"/pulls/{fields.number}/merge",
                payload,
            )
        )
        return _merge_result_from_json(response, fields.number)


class MockGitHubRepositoryAdapter:
    """In-memory GitHub adapter for local workflow tests."""

    def __init__(
        self,
        config: GitHubAdapterConfig,
        *,
        default_branch_sha: str = "0" * 40,
        private: bool = True,
    ) -> None:
        self.config = config
        self._private = private
        self._branches: dict[str, GitHubBranchMetadata] = {
            config.default_branch: GitHubBranchMetadata(
                name=config.default_branch,
                sha=default_branch_sha,
                protected=True,
            )
        }
        self._pull_requests: dict[int, GitHubPullRequestMetadata] = {}
        self._checks: dict[int, tuple[GitHubCheckRun, ...]] = {}
        self._next_pull_request_number = 1

    def validate_access(self) -> GitHubRepositoryConfiguration:
        return GitHubRepositoryConfiguration(
            repository=self.get_repository(),
            default_branch=self.get_branch(self.config.default_branch),
        )

    def get_repository(self) -> GitHubRepositoryMetadata:
        return GitHubRepositoryMetadata(
            full_name=self.config.repository,
            default_branch=self.config.default_branch,
            private=self._private,
            html_url=f"https://github.com/{self.config.repository}",
            clone_url=f"https://github.com/{self.config.repository}.git",
            ssh_url=f"git@github.com:{self.config.repository}.git",
            permissions={"admin": True, "maintain": True, "push": True, "pull": True},
            role_name="admin",
        )

    def get_branch(self, branch_name: str) -> GitHubBranchMetadata:
        branch = self._branches.get(branch_name)
        if branch is None:
            raise GitHubAdapterError(f"Mock GitHub branch does not exist: {branch_name}")
        return branch

    def create_branch(self, branch_name: str, from_ref: str) -> GitHubBranchMetadata:
        if branch_name in self._branches:
            raise GitHubAdapterError(f"Mock GitHub branch already exists: {branch_name}")
        source_sha = from_ref if _looks_like_sha(from_ref) else self.get_branch(_branch_name_from_ref(from_ref)).sha
        branch = GitHubBranchMetadata(name=branch_name, sha=source_sha)
        self._branches[branch_name] = branch
        return branch

    def create_pull_request(self, fields: GitHubPullRequestFields) -> GitHubPullRequestMetadata:
        head_branch = self.get_branch(fields.head)
        self.get_branch(fields.base)
        number = self._next_pull_request_number
        self._next_pull_request_number += 1
        pull_request = GitHubPullRequestMetadata(
            number=number,
            title=fields.title,
            head=fields.head,
            base=fields.base,
            state="open",
            draft=fields.draft,
            html_url=f"https://github.com/{self.config.repository}/pull/{number}",
            mergeable_state="unknown",
            head_sha=head_branch.sha,
        )
        self._pull_requests[number] = pull_request
        return pull_request

    def get_pull_request(self, number: int) -> GitHubPullRequestMetadata:
        pull_request = self._pull_requests.get(number)
        if pull_request is None:
            raise GitHubAdapterError(f"Mock GitHub pull request does not exist: {number}")
        return pull_request

    def get_pull_request_checks(self, number: int) -> GitHubPullRequestChecks:
        pull_request = self.get_pull_request(number)
        return GitHubPullRequestChecks(
            pull_request_number=number,
            head_sha=pull_request.head_sha,
            runs=self._checks.get(number, ()),
        )

    def set_pull_request_checks(self, number: int, runs: Sequence[GitHubCheckRun]) -> None:
        self.get_pull_request(number)
        self._checks[number] = tuple(runs)

    def merge_pull_request(self, fields: GitHubPullRequestMergeFields) -> GitHubPullRequestMergeResult:
        pull_request = self.get_pull_request(fields.number)
        if pull_request.state != "open":
            raise GitHubAdapterError(f"Mock GitHub pull request is not open: {fields.number}")
        self._pull_requests[fields.number] = replace(pull_request, state="closed")
        return GitHubPullRequestMergeResult(
            number=fields.number,
            merged=True,
            sha=pull_request.head_sha,
            message="Pull Request successfully merged",
        )


def github_config_from_settings(settings: object) -> GitHubAdapterConfig:
    """Build adapter config from PlatformSettings or GitHubSettings-like objects."""

    github = getattr(settings, "github", settings)
    return GitHubAdapterConfig(
        repository=getattr(github, "repository"),
        token=getattr(github, "token", ""),
        default_branch=getattr(github, "default_branch", "main"),
    )


def github_rest_adapter_from_settings(settings: object) -> GitHubRestRepositoryAdapter:
    """Create a GitHub REST adapter from PlatformSettings or GitHubSettings."""

    return GitHubRestRepositoryAdapter(github_config_from_settings(settings))


def redacted_github_config(config: GitHubAdapterConfig) -> Mapping[str, str]:
    """Return non-secret configuration values for logs and diagnostics."""

    return {
        "repository": config.repository,
        "default_branch": config.default_branch,
        "api_base_url": config.normalized_api_base_url,
        "token": "<redacted>" if config.token else "",
    }


def github_https_remote_url(config: GitHubAdapterConfig) -> str:
    """Return a token-safe HTTPS remote URL for the configured repository."""

    return f"https://github.com/{config.owner}/{config.name}.git"


def github_token_credential_output(
    config: GitHubAdapterConfig,
    credential_input: str,
    *,
    operation: str = "get",
) -> str:
    """Return Git credential-helper output without logging the token."""

    if operation != "get" or not config.token:
        return ""
    fields = _credential_fields(credential_input)
    protocol = fields.get("protocol", "https")
    host = fields.get("host", "github.com")
    if protocol != "https" or host != "github.com":
        return ""
    return "\n".join(
        (
            "protocol=https",
            "host=github.com",
            "username=x-access-token",
            f"password={config.token}",
            "",
        )
    )


def _repo_path(config: GitHubAdapterConfig) -> str:
    return (
        "/repos/"
        + urllib.parse.quote(config.owner, safe="")
        + "/"
        + urllib.parse.quote(config.name, safe="")
    )


def _credential_fields(raw: str) -> Mapping[str, str]:
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        fields[key.strip()] = value.strip()
    return fields


def _branch_name_from_ref(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


def _looks_like_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdefABCDEF" for character in value)


def _repository_from_json(raw: Mapping[str, Any], config: GitHubAdapterConfig) -> GitHubRepositoryMetadata:
    permissions = _dict(raw.get("permissions"))
    return GitHubRepositoryMetadata(
        full_name=str(raw.get("full_name") or config.repository),
        default_branch=str(raw.get("default_branch") or config.default_branch),
        private=bool(raw.get("private")),
        html_url=str(raw.get("html_url") or ""),
        clone_url=str(raw.get("clone_url") or ""),
        ssh_url=str(raw.get("ssh_url") or ""),
        permissions={str(key): bool(value) for key, value in permissions.items()},
        role_name=str(raw.get("role_name") or ""),
    )


def _branch_from_json(raw: Mapping[str, Any], *, fallback_name: str) -> GitHubBranchMetadata:
    commit = _dict(raw.get("commit"))
    return GitHubBranchMetadata(
        name=str(raw.get("name") or fallback_name),
        sha=str(commit.get("sha") or raw.get("sha") or ""),
        protected=bool(raw.get("protected")),
    )


def _pull_request_from_json(raw: Mapping[str, Any]) -> GitHubPullRequestMetadata:
    head = _dict(raw.get("head"))
    base = _dict(raw.get("base"))
    return GitHubPullRequestMetadata(
        number=int(raw.get("number") or 0),
        title=str(raw.get("title") or ""),
        head=str(head.get("ref") or ""),
        base=str(base.get("ref") or ""),
        state=str(raw.get("state") or ""),
        draft=bool(raw.get("draft")),
        html_url=str(raw.get("html_url") or ""),
        mergeable_state=str(raw.get("mergeable_state") or ""),
        head_sha=str(head.get("sha") or ""),
    )


def _merge_result_from_json(raw: Mapping[str, Any], number: int) -> GitHubPullRequestMergeResult:
    return GitHubPullRequestMergeResult(
        number=number,
        merged=bool(raw.get("merged")),
        sha=str(raw.get("sha") or ""),
        message=str(raw.get("message") or ""),
    )


def _check_run_from_json(raw: object) -> GitHubCheckRun:
    data = _dict(raw)
    return GitHubCheckRun(
        name=str(data.get("name") or ""),
        status=str(data.get("status") or ""),
        conclusion=str(data.get("conclusion") or ""),
        details_url=str(data.get("details_url") or data.get("html_url") or ""),
    )


def _github_error_message(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "response message unavailable"
    if not isinstance(data, dict):
        return "response message unavailable"
    message = data.get("message")
    return str(message) if message else "response message unavailable"


def _dict(raw: object) -> Mapping[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def _list(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []
