import io
import urllib.error
import urllib.request

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.integrations import (
    GitHubAdapterConfig,
    GitHubAdapterError,
    GitHubCheckRun,
    GitHubPullRequestMergeFields,
    GitHubPullRequestChecks,
    GitHubPullRequestFields,
    GitHubRestRepositoryAdapter,
    GitHubRestTransport,
    MockGitHubRepositoryAdapter,
    github_config_from_settings,
    github_https_remote_url,
    github_token_credential_output,
    redacted_github_config,
)


class RecordingGitHubTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def request(self, method: str, path: str, payload: object = None) -> object:
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/repos/ExampleOrg/example-repo":
            return {
                "full_name": "ExampleOrg/example-repo",
                "default_branch": "main",
                "private": True,
                "html_url": "https://github.com/ExampleOrg/example-repo",
                "clone_url": "https://github.com/ExampleOrg/example-repo.git",
                "ssh_url": "git@github.com:ExampleOrg/example-repo.git",
                "permissions": {"admin": False, "maintain": False, "push": True, "pull": True},
                "role_name": "write",
            }
        if method == "GET" and path == "/repos/ExampleOrg/example-repo/branches/main":
            return {
                "name": "main",
                "commit": {"sha": "a" * 40},
                "protected": True,
            }
        if method == "POST" and path == "/repos/ExampleOrg/example-repo/git/refs":
            return {
                "ref": "refs/heads/feature/AGENT-27-github-adapter",
                "object": {"sha": payload["sha"]},
            }
        if method == "POST" and path == "/repos/ExampleOrg/example-repo/pulls":
            return {
                "number": 16,
                "title": payload["title"],
                "state": "open",
                "draft": payload["draft"],
                "html_url": "https://github.com/ExampleOrg/example-repo/pull/16",
                "head": {"ref": payload["head"], "sha": "b" * 40},
                "base": {"ref": payload["base"]},
                "mergeable_state": "clean",
            }
        if method == "GET" and path == "/repos/ExampleOrg/example-repo/pulls/16":
            return {
                "number": 16,
                "title": "AGENT-27 adapter",
                "state": "open",
                "draft": False,
                "html_url": "https://github.com/ExampleOrg/example-repo/pull/16",
                "head": {"ref": "feature/AGENT-27-github-adapter", "sha": "b" * 40},
                "base": {"ref": "main"},
                "mergeable_state": "clean",
            }
        if method == "GET" and path == f"/repos/ExampleOrg/example-repo/commits/{'b' * 40}/check-runs":
            return {
                "check_runs": [
                    {
                        "name": "tests",
                        "status": "completed",
                        "conclusion": "success",
                        "details_url": "https://github.example/checks/1",
                    }
                ]
            }
        if method == "PUT" and path == "/repos/ExampleOrg/example-repo/pulls/16/merge":
            return {
                "merged": True,
                "sha": "f" * 40,
                "message": "Pull Request successfully merged",
            }
        raise AssertionError(f"Unexpected request: {method} {path}")


def github_adapter_with_transport() -> tuple[GitHubRestRepositoryAdapter, RecordingGitHubTransport]:
    transport = RecordingGitHubTransport()
    adapter = GitHubRestRepositoryAdapter(
        GitHubAdapterConfig(
            repository="ExampleOrg/example-repo",
            token="secret-token",
            default_branch="main",
        ),
        transport=transport,
    )
    return adapter, transport


def test_github_config_from_settings_uses_configured_repository() -> None:
    settings = settings_from_mapping(
        {
            "GITHUB_TOKEN": "secret-token",
            "GITHUB_REPOSITORY": "ExampleOrg/example-repo",
            "GITHUB_DEFAULT_BRANCH": "trunk",
        }
    )

    config = github_config_from_settings(settings)

    assert config.repository == "ExampleOrg/example-repo"
    assert config.owner == "ExampleOrg"
    assert config.name == "example-repo"
    assert config.default_branch == "trunk"
    assert config.token == "secret-token"


def test_github_config_requires_owner_name_repository_format() -> None:
    config = GitHubAdapterConfig(repository="missing-owner-or-name")

    try:
        _ = config.owner
    except GitHubAdapterError as exc:
        assert "owner/name" in str(exc)
    else:
        raise AssertionError("Expected repository format validation to fail.")


def test_github_config_normalizes_api_url() -> None:
    config = GitHubAdapterConfig(
        repository="ExampleOrg/example-repo",
        api_base_url="https://github.example/api/v3/",
    )

    assert config.normalized_api_base_url == "https://github.example/api/v3"


def test_redacted_github_config_never_exposes_token() -> None:
    config = GitHubAdapterConfig(
        repository="ExampleOrg/example-repo",
        token="super-secret",
        default_branch="main",
    )

    redacted = redacted_github_config(config)

    assert redacted["repository"] == "ExampleOrg/example-repo"
    assert redacted["token"] == "<redacted>"
    assert "super-secret" not in str(redacted)


def test_github_https_remote_url_does_not_embed_token() -> None:
    config = GitHubAdapterConfig(repository="ExampleOrg/example-repo", token="super-secret")

    remote_url = github_https_remote_url(config)

    assert remote_url == "https://github.com/ExampleOrg/example-repo.git"
    assert "super-secret" not in remote_url


def test_github_token_credential_output_returns_token_only_for_github_get() -> None:
    config = GitHubAdapterConfig(repository="ExampleOrg/example-repo", token="super-secret")

    output = github_token_credential_output(
        config,
        "protocol=https\nhost=github.com\n\n",
    )

    assert "username=x-access-token" in output
    assert "password=super-secret" in output


def test_github_token_credential_output_ignores_non_github_or_store_requests() -> None:
    config = GitHubAdapterConfig(repository="ExampleOrg/example-repo", token="super-secret")

    assert github_token_credential_output(config, "protocol=https\nhost=example.com\n\n") == ""
    assert github_token_credential_output(config, "protocol=https\nhost=github.com\n\n", operation="store") == ""
    assert github_token_credential_output(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo"),
        "protocol=https\nhost=github.com\n\n",
    ) == ""


def test_pull_request_fields_default_to_ready_for_review() -> None:
    fields = GitHubPullRequestFields(
        title="AGENT-27 adapter",
        head="feature/AGENT-27-github-adapter",
        base="main",
    )

    assert fields.draft is False
    assert fields.maintainer_can_modify is True


def test_pull_request_checks_report_completion_and_failures() -> None:
    passing = GitHubCheckRun(name="tests", status="completed", conclusion="success")
    failing = GitHubCheckRun(name="lint", status="completed", conclusion="failure")

    checks = GitHubPullRequestChecks(
        pull_request_number=27,
        head_sha="abc123",
        runs=(passing, failing),
    )

    assert checks.is_complete is True
    assert checks.has_failures is True


def test_pull_request_checks_without_runs_are_not_complete() -> None:
    checks = GitHubPullRequestChecks(pull_request_number=27, head_sha="abc123")

    assert checks.is_complete is False
    assert checks.has_failures is False


def test_github_rest_adapter_validates_repository_and_default_branch() -> None:
    adapter, transport = github_adapter_with_transport()

    configuration = adapter.validate_access()

    assert configuration.repository.full_name == "ExampleOrg/example-repo"
    assert configuration.repository.default_branch == "main"
    assert configuration.repository.has_write_permission is True
    assert configuration.repository.permissions["push"] is True
    assert configuration.repository.role_name == "write"
    assert configuration.default_branch.name == "main"
    assert configuration.default_branch.sha == "a" * 40
    assert ("GET", "/repos/ExampleOrg/example-repo", None) in transport.calls
    assert ("GET", "/repos/ExampleOrg/example-repo/branches/main", None) in transport.calls


def test_github_rest_adapter_creates_branch_from_branch_name() -> None:
    adapter, transport = github_adapter_with_transport()

    branch = adapter.create_branch("feature/AGENT-27-github-adapter", "main")

    create_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/repos/ExampleOrg/example-repo/git/refs"
    )
    assert create_payload["ref"] == "refs/heads/feature/AGENT-27-github-adapter"
    assert create_payload["sha"] == "a" * 40
    assert branch.name == "feature/AGENT-27-github-adapter"
    assert branch.sha == "a" * 40


def test_github_rest_adapter_creates_and_reads_pull_request() -> None:
    adapter, transport = github_adapter_with_transport()

    created = adapter.create_pull_request(
        GitHubPullRequestFields(
            title="AGENT-27 adapter",
            head="feature/AGENT-27-github-adapter",
            base="main",
            body="Open adapter PR",
            draft=True,
        )
    )
    fetched = adapter.get_pull_request(created.number)

    pr_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/repos/ExampleOrg/example-repo/pulls"
    )
    assert pr_payload["title"] == "AGENT-27 adapter"
    assert pr_payload["head"] == "feature/AGENT-27-github-adapter"
    assert pr_payload["base"] == "main"
    assert created.number == 16
    assert created.draft is True
    assert fetched.mergeable_state == "clean"


def test_github_rest_adapter_reads_pull_request_checks() -> None:
    adapter, _transport = github_adapter_with_transport()

    checks = adapter.get_pull_request_checks(16)

    assert checks.pull_request_number == 16
    assert checks.head_sha == "b" * 40
    assert checks.runs[0].name == "tests"
    assert checks.runs[0].conclusion == "success"
    assert checks.is_complete is True
    assert checks.has_failures is False


def test_github_rest_adapter_merges_pull_request() -> None:
    adapter, transport = github_adapter_with_transport()

    result = adapter.merge_pull_request(
        GitHubPullRequestMergeFields(
            number=16,
            commit_title="Merge pull request #16",
            commit_message="AGENT-48 review merge",
        )
    )

    merge_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "PUT" and path == "/repos/ExampleOrg/example-repo/pulls/16/merge"
    )
    assert merge_payload["commit_title"] == "Merge pull request #16"
    assert merge_payload["merge_method"] == "merge"
    assert result.merged is True
    assert result.sha == "f" * 40


def test_github_rest_transport_errors_do_not_expose_token(monkeypatch) -> None:
    def fail_urlopen(request, timeout):  # noqa: ANN001
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"message":"Bad credentials"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    transport = GitHubRestTransport(
        GitHubAdapterConfig(
            repository="ExampleOrg/example-repo",
            token="super-secret-token",
        )
    )

    try:
        transport.request("GET", "/repos/ExampleOrg/example-repo")
    except GitHubAdapterError as exc:
        assert "Bad credentials" in str(exc)
        assert "super-secret-token" not in str(exc)
    else:
        raise AssertionError("Expected GitHubAdapterError for HTTP error.")


def test_mock_github_adapter_supports_local_branch_and_pr_workflow() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(
            repository="ExampleOrg/example-repo",
            default_branch="main",
        ),
        default_branch_sha="c" * 40,
    )

    configuration = adapter.validate_access()
    branch = adapter.create_branch("feature/AGENT-27-github-adapter", "main")
    pull_request = adapter.create_pull_request(
        GitHubPullRequestFields(
            title="AGENT-27 adapter",
            head=branch.name,
            base=configuration.default_branch.name,
            draft=True,
        )
    )

    assert configuration.repository.full_name == "ExampleOrg/example-repo"
    assert branch.sha == "c" * 40
    assert pull_request.number == 1
    assert pull_request.head_sha == "c" * 40
    assert adapter.get_pull_request(1).html_url.endswith("/pull/1")


def test_mock_github_adapter_supports_check_run_fixtures() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo"),
        default_branch_sha="d" * 40,
    )
    adapter.create_branch("feature/checks", "main")
    pull_request = adapter.create_pull_request(
        GitHubPullRequestFields(
            title="Checks",
            head="feature/checks",
            base="main",
        )
    )

    adapter.set_pull_request_checks(
        pull_request.number,
        (GitHubCheckRun(name="tests", status="completed", conclusion="success"),),
    )

    checks = adapter.get_pull_request_checks(pull_request.number)

    assert checks.head_sha == "d" * 40
    assert checks.runs[0].name == "tests"
    assert checks.has_failures is False


def test_mock_github_adapter_merges_pull_request() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo"),
        default_branch_sha="f" * 40,
    )
    adapter.create_branch("feature/review", "main")
    pull_request = adapter.create_pull_request(
        GitHubPullRequestFields(
            title="Review",
            head="feature/review",
            base="main",
        )
    )

    result = adapter.merge_pull_request(
        GitHubPullRequestMergeFields(number=pull_request.number, commit_title="Merge review")
    )

    assert result.merged is True
    assert adapter.get_pull_request(pull_request.number).state == "closed"


def test_mock_github_adapter_rejects_pull_request_for_missing_branch() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo"),
        default_branch_sha="e" * 40,
    )

    try:
        adapter.create_pull_request(
            GitHubPullRequestFields(
                title="Missing branch",
                head="feature/missing",
                base="main",
            )
        )
    except GitHubAdapterError as exc:
        assert "branch does not exist" in str(exc)
    else:
        raise AssertionError("Expected missing mock branch to block pull request creation.")
