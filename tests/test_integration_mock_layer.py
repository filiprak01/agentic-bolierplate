from agentic_boilerplate.integrations import (
    IntegrationMockLayer,
    create_integration_mock_layer,
    seed_representative_integration_data,
)


def test_integration_mock_layer_creates_all_boundaries_without_credentials() -> None:
    layer = create_integration_mock_layer(
        github_repository="CustomOrg/custom-repo",
        jira_project_key="CUSTOM",
        jira_board_id="987",
        confluence_space_key="CUSTOMDOCS",
        confluence_parent_page_id="555",
    )

    assert isinstance(layer, IntegrationMockLayer)
    assert layer.github.config.repository == "CustomOrg/custom-repo"
    assert layer.github.config.token == ""
    assert layer.jira.config.project_key == "CUSTOM"
    assert layer.jira.config.board_id == "987"
    assert layer.jira.config.api_token == ""
    assert layer.confluence.config.space_key == "CUSTOMDOCS"
    assert layer.confluence.config.parent_page_id == "555"
    assert layer.confluence.config.api_token == ""


def test_integration_mock_layer_validates_access_locally() -> None:
    layer = create_integration_mock_layer()

    github = layer.github.validate_access()
    jira = layer.jira.validate_access()
    confluence = layer.confluence.validate_access()

    assert github.repository.full_name == "ExampleOrg/example-repo"
    assert github.default_branch.name == "main"
    assert jira.project.key == "MOCK"
    assert jira.board.project_key == "MOCK"
    assert confluence.space.key == "DOCS"
    assert confluence.parent_page.id == "12345"


def test_representative_seed_data_covers_workflow_boundaries() -> None:
    layer = create_integration_mock_layer()

    seed = seed_representative_integration_data(layer)

    searched = layer.jira.search_issues("project = MOCK")
    blocker = next(issue for issue in searched if issue.key == seed.jira_blocker_key)
    blocked = next(issue for issue in searched if issue.key == seed.jira_blocked_key)
    dependency_links = layer.jira.get_dependency_links(seed.jira_blocked_key)
    pull_request = layer.github.get_pull_request(seed.github_pull_request_number)
    checks = layer.github.get_pull_request_checks(seed.github_pull_request_number)
    page = layer.confluence.get_page(seed.confluence_page_id)

    assert blocker.status == "DEV COMPLETED"
    assert blocked.status == "READY TO START"
    assert dependency_links.blockers == (seed.jira_blocker_key,)
    assert dependency_links.is_blocked is True
    assert pull_request.head == seed.github_feature_branch
    assert pull_request.base == "main"
    assert pull_request.draft is False
    assert checks.is_complete is True
    assert checks.has_failures is False
    assert [run.name for run in checks.runs] == ["lint", "tests"]
    assert page.title == "Seeded Shared Context"
    assert "Jira dependencies" in page.body_storage


def test_seeded_contract_runs_without_external_credentials(monkeypatch, tmp_path) -> None:
    for variable in (
        "GITHUB_TOKEN",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "CONFLUENCE_EMAIL",
        "CONFLUENCE_API_TOKEN",
    ):
        monkeypatch.delenv(variable, raising=False)
    layer = create_integration_mock_layer(
        github_repository="AnotherOrg/another-repo",
        jira_project_key="ALT",
        jira_board_id="42",
        confluence_space_key="ALTSPACE",
        confluence_parent_page_id="999",
    )

    seed = seed_representative_integration_data(layer)
    mirrored = layer.confluence.mirror_page(
        layer.confluence.get_page(seed.confluence_page_id),
        tmp_path,
    )

    assert layer.github.config.token == ""
    assert layer.jira.config.email == ""
    assert layer.jira.config.api_token == ""
    assert layer.confluence.config.email == ""
    assert layer.confluence.config.api_token == ""
    assert layer.github.get_branch(seed.github_feature_branch).name.startswith("feature/ALT-")
    assert [issue.key for issue in layer.jira.search_issues("project = ALT")] == ["ALT-1", "ALT-2"]
    assert layer.jira.search_issues("project = MOCK") == ()
    assert mirrored.path.exists()
    assert mirrored.path.read_text(encoding="utf-8").startswith("# Seeded Shared Context")
