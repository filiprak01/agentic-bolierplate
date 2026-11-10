from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain.dependency_eligibility import (
    DependencyBlockerKind,
    check_dependency_eligibility,
)
from agentic_boilerplate.integrations import (
    JiraAdapterConfig,
    JiraAdapterError,
    JiraCloudProjectIssueAdapter,
    JiraIssueDependencyLinks,
    JiraIssueFields,
    JiraLinkedIssue,
    JiraTransition,
    JiraIssueUpdate,
    MockJiraProjectIssueAdapter,
    JiraSprint,
    adf_from_text,
    jira_config_from_settings,
    text_from_adf,
)


class RecordingTransport:
    def __init__(self, *, project_key: str = "CUSTOM", board_project_key: str = "CUSTOM") -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.project_key = project_key
        self.board_project_key = board_project_key

    def request(self, method: str, path: str, payload: object = None) -> object:
        self.calls.append((method, path, payload))
        if path == "/rest/agile/1.0/board/987/sprint?maxResults=50&state=active":
            return {
                "values": [
                    {
                        "id": 44,
                        "name": "Sprint 44",
                        "state": "active",
                        "goal": "Ship hardening",
                        "startDate": "2026-07-01T09:00:00.000Z",
                        "endDate": "2026-07-07T18:00:00.000Z",
                        "originBoardId": 987,
                    }
                ]
            }
        if path.startswith("/rest/api/3/project/"):
            return {
                "id": "10001",
                "key": self.project_key,
                "name": "Custom Project",
                "issueTypes": [
                    {"id": "1", "name": "Story", "subtask": False},
                    {"id": "2", "name": "Subtask", "subtask": True},
                ],
            }
        if path.startswith("/rest/agile/1.0/board/"):
            return {
                "id": 987,
                "name": "Custom Scrum",
                "type": "scrum",
                "location": {"projectKey": self.board_project_key},
            }
        if path == "/rest/agile/1.0/sprint/44" and method == "GET":
            return {
                "id": 44,
                "name": "Sprint 44",
                "state": "active",
                "goal": "Ship hardening",
                "startDate": "2026-07-01T09:00:00.000Z",
                "endDate": "2026-07-07T18:00:00.000Z",
                "originBoardId": 987,
            }
        if path == "/rest/agile/1.0/sprint/44/issue?maxResults=100&fields=summary%2Cstatus%2Cissuetype%2Clabels%2Cparent":
            return {
                "issues": [
                    {
                        "key": "CUSTOM-1",
                        "fields": {
                            "summary": "Configurable issue",
                            "issuetype": {"name": "Story"},
                            "status": {"name": "FUNNEL"},
                            "labels": ["configured-project"],
                        },
                    },
                    {
                        "key": "CUSTOM-2",
                        "fields": {
                            "summary": "Created issue",
                            "issuetype": {"name": "Task"},
                            "status": {"name": "READY TO START"},
                            "labels": ["support"],
                        },
                    },
                ]
            }
        if path == "/rest/agile/1.0/sprint/44/issue" and method == "POST":
            return {}
        if path == "/rest/agile/1.0/sprint/44" and method == "PUT":
            return {
                "id": 44,
                "name": "Sprint 44",
                "state": payload["state"],
                "goal": "Ship hardening",
                "startDate": payload.get("startDate", "2026-07-01T09:00:00.000Z"),
                "endDate": payload.get("endDate", "2026-07-07T18:00:00.000Z"),
                "completeDate": "2026-07-07T18:30:00.000Z" if payload["state"] == "closed" else "",
                "originBoardId": 987,
            }
        if path == "/rest/api/3/status":
            return [{"id": "10", "name": "FUNNEL", "statusCategory": {"name": "To Do"}}]
        if path == "/rest/api/3/priority":
            return [{"id": "3", "name": "Medium"}]
        if path == "/rest/api/3/issueLinkType":
            return {
                "issueLinkTypes": [
                    {"id": "10000", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"}
                ]
            }
        if path.startswith("/rest/api/3/search/jql?"):
            return {
                "issues": [
                    {
                        "key": "CUSTOM-1",
                        "fields": {
                            "summary": "Configurable issue",
                            "issuetype": {"name": "Story"},
                            "status": {"name": "FUNNEL"},
                            "labels": ["configured-project"],
                        },
                    }
                ]
            }
        if path == "/rest/api/3/issue" and method == "POST":
            return {"key": "CUSTOM-2"}
        if path == "/rest/api/3/issue/CUSTOM-2/transitions" and method == "GET":
            return {
                "transitions": [
                    {"id": "21", "name": "Start Progress", "to": {"name": "IN PROGRESS"}},
                    {"id": "31", "name": "Dev completed", "to": {"name": "DEV COMPLETED"}},
                ]
            }
        if path == "/rest/api/3/issue/CUSTOM-2/transitions" and method == "POST":
            return {}
        if path == "/rest/api/3/issue/CUSTOM-2?fields=issuelinks" and method == "GET":
            return {
                "key": "CUSTOM-2",
                "fields": {
                    "issuelinks": [
                        {
                            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                            "inwardIssue": {
                                "key": "CUSTOM-1",
                                "fields": {
                                    "summary": "Prerequisite",
                                    "issuetype": {"name": "Story"},
                                    "status": {"name": "TEST COMPLETED"},
                                    "labels": ["dependency"],
                                },
                            },
                        },
                        {
                            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                            "outwardIssue": {
                                "key": "CUSTOM-3",
                                "fields": {
                                    "summary": "Dependent",
                                    "issuetype": {"name": "Story"},
                                    "status": {"name": "READY TO START"},
                                },
                            },
                        },
                        {
                            "type": {"name": "Problem", "inward": "is caused by", "outward": "causes"},
                            "outwardIssue": {
                                "key": "CUSTOM-8",
                                "fields": {
                                    "summary": "Regression bug",
                                    "issuetype": {"name": "Bug"},
                                    "status": {"name": "IN PROGRESS"},
                                },
                            },
                        },
                        {
                            "type": {"name": "Relates", "inward": "relates to", "outward": "relates to"},
                            "outwardIssue": {"key": "CUSTOM-9"},
                        },
                    ]
                },
            }
        if path == "/rest/api/3/issue/CUSTOM-1?fields=issuelinks" and method == "GET":
            return {
                "key": "CUSTOM-1",
                "fields": {
                    "issuelinks": [
                        {
                            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                            "outwardIssue": {
                                "key": "CUSTOM-2",
                                "fields": {
                                    "summary": "Dependent",
                                    "issuetype": {"name": "Story"},
                                    "status": {"name": "READY TO START"},
                                },
                            },
                        }
                    ]
                },
            }
        if path == "/rest/api/3/issue/CUSTOM-3?fields=issuelinks" and method == "GET":
            return {
                "key": "CUSTOM-3",
                "fields": {
                    "issuelinks": [
                        {
                            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                            "inwardIssue": {
                                "key": "CUSTOM-2",
                                "fields": {
                                    "summary": "Prerequisite",
                                    "issuetype": {"name": "Story"},
                                    "status": {"name": "IN PROGRESS"},
                                },
                            },
                        }
                    ]
                },
            }
        if path == "/rest/api/3/issue/CUSTOM-4?fields=issuelinks" and method == "GET":
            return {
                "key": "CUSTOM-4",
                "fields": {
                    "issuelinks": [
                        {
                            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                            "inwardIssue": {
                                "key": "CUSTOM-0",
                                "fields": {
                                    "summary": "Incomplete prerequisite snapshot",
                                    "issuetype": {"name": "Story"},
                                },
                            },
                        }
                    ]
                },
            }
        if path.startswith("/rest/api/3/issue/CUSTOM-2") and method == "GET":
            return {
                "key": "CUSTOM-2",
                "fields": {
                    "summary": "Created issue",
                    "issuetype": {"name": "Story"},
                    "status": {"name": "FUNNEL"},
                    "labels": ["updated"],
                },
            }
        if path.startswith("/rest/api/3/issue/CUSTOM-2") and method == "PUT":
            return {}
        if path == "/rest/api/3/issueLink" and method == "POST":
            return {}
        raise AssertionError(f"Unexpected request: {method} {path}")


def test_jira_config_from_settings_is_project_and_board_configurable() -> None:
    first = settings_from_mapping(
        {
            "JIRA_BASE_URL": "https://example.atlassian.net",
            "JIRA_PROJECT_KEY": "ONE",
            "JIRA_BOARD_ID": "101",
            "JIRA_EMAIL": "po-one@example.com",
            "JIRA_API_TOKEN": "token-one",
        }
    )
    second = settings_from_mapping(
        {
            "JIRA_BASE_URL": "https://example.atlassian.net",
            "JIRA_PROJECT_KEY": "TWO",
            "JIRA_BOARD_ID": "202",
            "JIRA_EMAIL": "po-two@example.com",
            "JIRA_API_TOKEN": "token-two",
        }
    )

    first_config = jira_config_from_settings(first)
    second_config = jira_config_from_settings(second)

    assert first_config.project_key == "ONE"
    assert first_config.board_id == "101"
    assert second_config.project_key == "TWO"
    assert second_config.board_id == "202"
    assert first_config != second_config


def test_jira_adapter_config_normalizes_base_url_without_hardcoded_project() -> None:
    config = JiraAdapterConfig(
        base_url="https://example.atlassian.net/",
        project_key="CUSTOM",
        board_id="987",
    )

    assert config.normalized_base_url == "https://example.atlassian.net"
    assert config.project_key == "CUSTOM"
    assert config.board_id == "987"
    assert config.default_issue_status == "FUNNEL"


def test_jira_issue_fields_keep_issue_type_and_parent_configurable() -> None:
    fields = JiraIssueFields(
        summary="Create adapter",
        issue_type="Custom Story",
        description="Use configured issue type",
        labels=("configured-project",),
        parent_key="CUSTOM-1",
    )

    assert fields.issue_type == "Custom Story"
    assert fields.parent_key == "CUSTOM-1"
    assert fields.labels == ("configured-project",)


def test_jira_workflow_contract_models_transitions_and_dependencies() -> None:
    transition = JiraTransition(id="21", name="Start Progress", to_status="IN PROGRESS")
    links = JiraIssueDependencyLinks(
        issue_key="CUSTOM-2",
        blockers=("CUSTOM-1",),
        blocked=("CUSTOM-3",),
        blocker_issues=(JiraLinkedIssue(key="CUSTOM-1", status="TEST COMPLETED"),),
    )

    assert transition.to_status == "IN PROGRESS"
    assert links.is_blocked is True
    assert links.blockers == ("CUSTOM-1",)
    assert links.blocked == ("CUSTOM-3",)


def test_plain_text_adf_round_trip_supports_descriptions() -> None:
    document = adf_from_text("Line one\n\nLine two")

    assert document["type"] == "doc"
    assert text_from_adf(document) == "Line one\n\nLine two"


def test_jira_cloud_adapter_reads_configured_project_board_and_metadata() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    metadata = adapter.validate_access()

    assert metadata.project.key == "CUSTOM"
    assert metadata.board.id == "987"
    assert metadata.board.project_key == "CUSTOM"
    assert [issue_type.name for issue_type in metadata.issue_types] == ["Story", "Subtask"]
    assert metadata.statuses[0].name == "FUNNEL"
    assert metadata.link_types[0].name == "Blocks"
    assert ("GET", "/rest/api/3/project/CUSTOM", None) in transport.calls
    assert ("GET", "/rest/agile/1.0/board/987", None) in transport.calls


def test_jira_cloud_adapter_rejects_board_from_different_project() -> None:
    transport = RecordingTransport(board_project_key="OTHER")
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    try:
        adapter.validate_access()
    except JiraAdapterError as exc:
        assert "does not belong to the configured project" in str(exc)
    else:
        raise AssertionError("Expected JiraAdapterError for mismatched board project.")


def test_jira_cloud_adapter_search_uses_jira_cloud_jql_endpoint() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    issues = adapter.search_issues(
        "project = CUSTOM ORDER BY key ASC",
        fields=("summary", "status"),
    )

    assert issues[0].key == "CUSTOM-1"
    assert issues[0].summary == "Configurable issue"
    assert any(
        method == "GET"
        and path.startswith("/rest/api/3/search/jql?")
        and "project+%3D+CUSTOM" in path
        for method, path, _payload in transport.calls
    )


def test_jira_cloud_adapter_create_and_update_issue_use_configured_project() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    created = adapter.create_issue(
        JiraIssueFields(
            summary="Created issue",
            issue_type="Story",
            description="Created from adapter",
            labels=("configured-project",),
        )
    )
    updated = adapter.update_issue(
        created.key,
        JiraIssueUpdate(description="Updated description", labels=("updated",)),
    )

    create_payload = next(payload for method, path, payload in transport.calls if method == "POST" and path == "/rest/api/3/issue")
    assert create_payload["fields"]["project"]["key"] == "CUSTOM"
    assert create_payload["fields"]["issuetype"]["name"] == "Story"
    assert created.key == "CUSTOM-2"
    assert updated.labels == ("updated",)


def test_jira_cloud_adapter_reads_and_applies_transitions() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    transitions = adapter.get_transitions("CUSTOM-2")
    transitioned = adapter.transition_issue("CUSTOM-2", "DEV COMPLETED")

    transition_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/rest/api/3/issue/CUSTOM-2/transitions"
    )
    assert [transition.to_status for transition in transitions] == ["IN PROGRESS", "DEV COMPLETED"]
    assert transition_payload["transition"]["id"] == "31"
    assert transitioned.key == "CUSTOM-2"


def test_jira_cloud_adapter_creates_blocks_link_with_verified_direction() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    adapter.create_blocks_link("CUSTOM-1", "CUSTOM-2")

    link_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/rest/api/3/issueLink"
    )
    assert link_payload["type"]["name"] == "Blocks"
    assert link_payload["inwardIssue"]["key"] == "CUSTOM-1"
    assert link_payload["outwardIssue"]["key"] == "CUSTOM-2"


def test_jira_cloud_adapter_reads_dependency_links_for_scheduler() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    links = adapter.get_dependency_links("CUSTOM-2")

    assert links.issue_key == "CUSTOM-2"
    assert links.blockers == ("CUSTOM-1",)
    assert links.blocked == ("CUSTOM-3",)
    assert links.is_blocked is True
    assert links.blocker_issues[0].status == "TEST COMPLETED"
    assert links.blocker_issues[0].issue_type == "Story"
    assert links.linked_bugs[0].key == "CUSTOM-8"
    assert links.linked_bugs[0].status == "IN PROGRESS"


def test_jira_cloud_adapter_interprets_raw_blocks_link_from_both_issue_perspectives() -> None:
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=RecordingTransport(),
    )

    blocker_view = adapter.get_dependency_links("CUSTOM-1")
    blocked_view = adapter.get_dependency_links("CUSTOM-3")

    assert blocker_view.blockers == ()
    assert blocker_view.blocked == ("CUSTOM-2",)
    assert blocked_view.blockers == ("CUSTOM-2",)
    assert blocked_view.blocked == ()


def test_jira_cloud_adapter_keeps_unknown_prerequisite_status_fail_closed() -> None:
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=RecordingTransport(),
    )

    links = adapter.get_dependency_links("CUSTOM-4")
    eligibility = check_dependency_eligibility(links)

    assert links.blockers == ("CUSTOM-0",)
    assert links.blocker_issues[0].status == ""
    assert eligibility.eligible is False
    assert eligibility.blockers[0].kind is DependencyBlockerKind.UNKNOWN_PREREQUISITE_STATUS


def test_jira_cloud_adapter_reads_and_updates_sprint_lifecycle() -> None:
    transport = RecordingTransport()
    adapter = JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )

    sprints = adapter.list_sprints(state="active")
    sprint = adapter.get_sprint("44")
    sprint_issues = adapter.get_sprint_issues("44")
    added = adapter.add_issues_to_sprint("44", ("CUSTOM-1", "CUSTOM-2"))
    closed = adapter.transition_sprint("44", "closed", name="Sprint 44")

    assert sprints[0].state == "active"
    assert sprint.id == "44"
    assert [issue.key for issue in sprint_issues] == ["CUSTOM-1", "CUSTOM-2"]
    assert added == ("CUSTOM-1", "CUSTOM-2")
    assert closed.state == "closed"
    assert any(
        method == "GET" and path == "/rest/agile/1.0/board/987/sprint?maxResults=50&state=active"
        for method, path, _payload in transport.calls
    )
    add_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/rest/agile/1.0/sprint/44/issue"
    )
    assert add_payload == {"issues": ["CUSTOM-1", "CUSTOM-2"]}
    close_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "PUT" and path == "/rest/agile/1.0/sprint/44"
    )
    assert close_payload == {
        "state": "closed",
        "name": "Sprint 44",
        "goal": "Ship hardening",
        "startDate": "2026-07-01T09:00:00.000Z",
        "endDate": "2026-07-07T18:00:00.000Z",
    }


def test_mock_jira_adapter_keeps_project_issue_keys_isolated() -> None:
    first = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="ONE",
            board_id="101",
        )
    )
    second = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="TWO",
            board_id="202",
        )
    )

    one_issue = first.create_issue(JiraIssueFields(summary="One", issue_type="Story"))
    two_issue = second.create_issue(JiraIssueFields(summary="Two", issue_type="Story"))

    assert one_issue.key == "ONE-1"
    assert two_issue.key == "TWO-1"
    assert [issue.key for issue in first.search_issues("project = ONE")] == ["ONE-1"]
    assert [issue.key for issue in second.search_issues("project = TWO")] == ["TWO-1"]
    assert first.search_issues("project = TWO") == ()


def test_mock_jira_adapter_exposes_configured_metadata() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="OPS",
            board_id="303",
            default_issue_status="Intake",
            subtask_issue_type="Implementation Step",
        ),
        statuses=("Intake", "Ready", "Doing"),
        issue_types=("Feature", "Implementation Step"),
    )

    metadata = adapter.validate_access()

    assert metadata.project.key == "OPS"
    assert metadata.board.id == "303"
    assert [status.name for status in metadata.statuses] == ["Intake", "Ready", "Doing"]
    assert metadata.issue_types[1].name == "Implementation Step"
    assert metadata.issue_types[1].subtask is True


def test_mock_jira_adapter_transitions_issue_status() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="OPS",
            board_id="303",
            default_issue_status="FUNNEL",
        ),
        statuses=("FUNNEL", "READY TO START", "IN PROGRESS"),
    )
    issue = adapter.create_issue(JiraIssueFields(summary="Transition me", issue_type="Story"))

    transitions = adapter.get_transitions(issue.key)
    transitioned = adapter.transition_issue(issue.key, "IN PROGRESS")

    assert [transition.to_status for transition in transitions] == [
        "FUNNEL",
        "READY TO START",
        "IN PROGRESS",
    ]
    assert transitioned.status == "IN PROGRESS"


def test_mock_jira_adapter_tracks_blocks_direction_for_scheduler() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="OPS",
            board_id="303",
        )
    )
    blocker = adapter.create_issue(JiraIssueFields(summary="Prerequisite", issue_type="Story"))
    blocked = adapter.create_issue(JiraIssueFields(summary="Dependent", issue_type="Story"))

    adapter.create_blocks_link(blocker.key, blocked.key)

    blocked_links = adapter.get_dependency_links(blocked.key)
    blocker_links = adapter.get_dependency_links(blocker.key)
    assert blocked_links.blockers == (blocker.key,)
    assert blocked_links.blocked == ()
    assert blocked_links.is_blocked is True
    assert blocker_links.blockers == ()
    assert blocker_links.blocked == (blocked.key,)


def test_mock_jira_adapter_tracks_sprint_membership_and_lifecycle() -> None:
    adapter = MockJiraProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="OPS",
            board_id="303",
        ),
        sprints=(
            JiraSprint(
                id="44",
                name="Sprint 44",
                state="future",
                start_date="2026-07-01T09:00:00.000Z",
                end_date="2026-07-07T18:00:00.000Z",
                origin_board_id="303",
            ),
        ),
    )
    story = adapter.create_issue(JiraIssueFields(summary="Feature", issue_type="Story"))
    task = adapter.create_issue(JiraIssueFields(summary="Retro", issue_type="Task"))

    listed = adapter.list_sprints(state="future")
    added = adapter.add_issues_to_sprint("44", (story.key, task.key))
    sprint_issues = adapter.get_sprint_issues("44")
    active = adapter.transition_sprint("44", "active", name="Sprint 44 renamed")
    closed = adapter.transition_sprint("44", "closed")

    assert listed[0].id == "44"
    assert added == (story.key, task.key)
    assert [issue.key for issue in sprint_issues] == [story.key, task.key]
    assert active.state == "active"
    assert active.name == "Sprint 44 renamed"
    assert closed.state == "closed"
    assert closed.name == "Sprint 44 renamed"
    assert closed.complete_date == "mock-now"
