# Integration Mock Layer

The integration mock layer provides local GitHub, Jira, and Confluence adapters
for contract tests that must not call external services or require credentials.

Use `create_integration_mock_layer()` when a test needs all three integration
boundaries available together:

```python
from agentic_boilerplate.integrations import create_integration_mock_layer

layer = create_integration_mock_layer(
    github_repository="ExampleOrg/example-repo",
    jira_project_key="EXAMPLE",
    jira_board_id="42",
    confluence_space_key="DOCS",
    confluence_parent_page_id="12345",
)
```

The returned layer exposes:

1. `layer.github` as a `MockGitHubRepositoryAdapter`.
2. `layer.jira` as a `MockJiraProjectIssueAdapter`.
3. `layer.confluence` as a `MockConfluenceDocumentationAdapter`.

The default configs intentionally leave tokens, emails, and API credentials
empty. Tests that use this layer should remain local-only.

## Representative Seed Data

Use `seed_representative_integration_data(layer)` when a test needs realistic
workflow data across all adapters.

The seed creates:

1. Jira prerequisite and dependent Story issues.
2. A Jira `Blocks` link from the prerequisite story to the dependent story.
3. Jira statuses covering the delivery workflow, including `READY TO START`,
   `DEV COMPLETED`, `TEST COMPLETED`, and `ACCEPTED/DONE`.
4. A GitHub feature branch and open pull request.
5. Passing GitHub `lint` and `tests` check runs.
6. A Confluence child page that can be read or mirrored.

The seed returns stable keys and identifiers so tests can assert behavior
without relying on private mock internals.

## Contract Test Expectations

Contract tests should use public adapter methods only. Avoid inspecting private
mock dictionaries or counters.

Recommended assertions:

1. Access validation returns project, board, repository, branch, space, and
   parent-page metadata.
2. Jira searches are scoped to the configured project key.
3. Jira dependency links identify blocked work.
4. GitHub pull requests expose head branch, base branch, draft state, and check
   completion.
5. Confluence pages can be read and mirrored into temporary local storage.

This layer is for local contract tests and future worker simulations. It is not
a replacement for live adapter smoke checks against configured projects.
