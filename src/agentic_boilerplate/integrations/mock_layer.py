"""Shared mock integration layer for local contract tests."""

from __future__ import annotations

from dataclasses import dataclass

from agentic_boilerplate.integrations.confluence import (
    ConfluenceAdapterConfig,
    ConfluencePageFields,
    MockConfluenceDocumentationAdapter,
)
from agentic_boilerplate.integrations.github import (
    GitHubAdapterConfig,
    GitHubCheckRun,
    GitHubPullRequestFields,
    MockGitHubRepositoryAdapter,
)
from agentic_boilerplate.integrations.jira import (
    JiraAdapterConfig,
    JiraIssueFields,
    MockJiraProjectIssueAdapter,
)


@dataclass(frozen=True)
class IntegrationMockLayer:
    """In-memory adapters for GitHub, Jira, and Confluence contract tests."""

    github: MockGitHubRepositoryAdapter
    jira: MockJiraProjectIssueAdapter
    confluence: MockConfluenceDocumentationAdapter


@dataclass(frozen=True)
class IntegrationMockSeed:
    """Keys and identifiers created by representative mock seed data."""

    jira_blocker_key: str
    jira_blocked_key: str
    github_feature_branch: str
    github_pull_request_number: int
    confluence_page_id: str


def create_integration_mock_layer(
    *,
    github_repository: str = "ExampleOrg/example-repo",
    github_default_branch: str = "main",
    jira_base_url: str = "https://example.atlassian.net",
    jira_project_key: str = "MOCK",
    jira_board_id: str = "1",
    confluence_base_url: str = "https://example.atlassian.net/wiki",
    confluence_space_key: str = "DOCS",
    confluence_parent_page_id: str = "12345",
) -> IntegrationMockLayer:
    """Create local integration mocks without requiring external credentials."""

    return IntegrationMockLayer(
        github=MockGitHubRepositoryAdapter(
            GitHubAdapterConfig(
                repository=github_repository,
                default_branch=github_default_branch,
            )
        ),
        jira=MockJiraProjectIssueAdapter(
            JiraAdapterConfig(
                base_url=jira_base_url,
                project_key=jira_project_key,
                board_id=jira_board_id,
            ),
            statuses=(
                "FUNNEL",
                "READY TO START",
                "IN PROGRESS",
                "DEV COMPLETED",
                "IN TESTING",
                "TEST COMPLETED",
                "ACCEPTED/DONE",
            ),
        ),
        confluence=MockConfluenceDocumentationAdapter(
            ConfluenceAdapterConfig(
                base_url=confluence_base_url,
                space_key=confluence_space_key,
                parent_page_id=confluence_parent_page_id,
            )
        ),
    )


def seed_representative_integration_data(layer: IntegrationMockLayer) -> IntegrationMockSeed:
    """Seed reusable data for cross-adapter contract tests."""

    blocker = layer.jira.create_issue(
        JiraIssueFields(
            summary="Prepare prerequisite workflow",
            issue_type=layer.jira.config.story_issue_type,
            labels=("seeded-integration", "prerequisite"),
        )
    )
    blocked = layer.jira.create_issue(
        JiraIssueFields(
            summary="Implement dependent workflow",
            issue_type=layer.jira.config.story_issue_type,
            labels=("seeded-integration", "blocked"),
        )
    )
    layer.jira.create_blocks_link(blocker.key, blocked.key)
    layer.jira.transition_issue(blocker.key, "DEV COMPLETED")
    layer.jira.transition_issue(blocked.key, "READY TO START")

    feature_branch = f"feature/{blocked.key}-seeded-contract"
    layer.github.create_branch(feature_branch, layer.github.config.default_branch)
    pull_request = layer.github.create_pull_request(
        GitHubPullRequestFields(
            title=f"{blocked.key} seeded integration contract",
            head=feature_branch,
            base=layer.github.config.default_branch,
            body="Seeded PR for local integration contract tests.",
            draft=False,
        )
    )
    layer.github.set_pull_request_checks(
        pull_request.number,
        (
            GitHubCheckRun(name="lint", status="completed", conclusion="success"),
            GitHubCheckRun(name="tests", status="completed", conclusion="success"),
        ),
    )

    page = layer.confluence.create_or_update_child_page(
        ConfluencePageFields(
            title="Seeded Shared Context",
            body_storage=(
                "<p>Seeded integration data covers Jira dependencies, "
                "GitHub PR checks, and Confluence page reads.</p>"
            ),
        )
    )

    return IntegrationMockSeed(
        jira_blocker_key=blocker.key,
        jira_blocked_key=blocked.key,
        github_feature_branch=feature_branch,
        github_pull_request_number=pull_request.number,
        confluence_page_id=page.id,
    )
