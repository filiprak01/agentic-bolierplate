"""Configurable Jira integration boundary."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class JiraAdapterError(RuntimeError):
    """Raised when Jira adapter operations fail."""


class JiraTransport(Protocol):
    """HTTP transport used by the Jira Cloud adapter."""

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Send one Jira request and return a decoded JSON object."""


@dataclass(frozen=True)
class JiraAdapterConfig:
    """Configuration for one target Jira project and board."""

    base_url: str
    project_key: str
    board_id: str
    email: str = ""
    api_token: str = ""
    default_issue_status: str = "FUNNEL"
    story_issue_type: str = "Story"
    task_issue_type: str = "Task"
    bug_issue_type: str = "Bug"
    test_issue_type: str = "Test"
    subtask_issue_type: str = "Subtask"
    blocks_link_type: str = "Blocks"

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


@dataclass(frozen=True)
class JiraStatus:
    id: str
    name: str
    category: str = ""


@dataclass(frozen=True)
class JiraIssueType:
    id: str
    name: str
    subtask: bool = False


@dataclass(frozen=True)
class JiraPriority:
    id: str
    name: str


@dataclass(frozen=True)
class JiraLinkType:
    id: str
    name: str
    inward: str = ""
    outward: str = ""


@dataclass(frozen=True)
class JiraProjectMetadata:
    key: str
    name: str
    id: str = ""
    issue_types: tuple[JiraIssueType, ...] = ()


@dataclass(frozen=True)
class JiraBoardMetadata:
    id: str
    name: str
    type: str = ""
    project_key: str = ""


@dataclass(frozen=True)
class JiraIssueFields:
    summary: str
    issue_type: str
    description: str = ""
    labels: tuple[str, ...] = ()
    parent_key: str = ""


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str
    issue_type: str
    status: str = ""
    labels: tuple[str, ...] = ()
    parent_key: str = ""


@dataclass(frozen=True)
class JiraSprint:
    id: str
    name: str
    state: str
    goal: str = ""
    start_date: str = ""
    end_date: str = ""
    complete_date: str = ""
    origin_board_id: str = ""


@dataclass(frozen=True)
class JiraLinkedIssue:
    key: str
    summary: str = ""
    issue_type: str = ""
    status: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class JiraIssueUpdate:
    description: str | None = None
    labels: tuple[str, ...] | None = None


@dataclass(frozen=True)
class JiraTransition:
    id: str
    name: str
    to_status: str = ""


@dataclass(frozen=True)
class JiraIssueDependencyLinks:
    issue_key: str
    blockers: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    blocker_issues: tuple[JiraLinkedIssue, ...] = ()
    blocked_issues: tuple[JiraLinkedIssue, ...] = ()
    linked_bugs: tuple[JiraLinkedIssue, ...] = ()

    @property
    def is_blocked(self) -> bool:
        return bool(self.blockers)


@dataclass(frozen=True)
class JiraProjectConfiguration:
    project: JiraProjectMetadata
    board: JiraBoardMetadata
    statuses: tuple[JiraStatus, ...]
    issue_types: tuple[JiraIssueType, ...]
    priorities: tuple[JiraPriority, ...]
    link_types: tuple[JiraLinkType, ...]


class JiraProjectIssueAdapter(Protocol):
    """Configurable Jira project and issue adapter contract."""

    config: JiraAdapterConfig

    def validate_access(self) -> JiraProjectConfiguration:
        """Read configured project metadata and fail when access is not valid."""

    def search_issues(self, jql: str, *, fields: Sequence[str] = ()) -> tuple[JiraIssue, ...]:
        """Search issues using Jira Cloud JQL."""

    def create_issue(self, fields: JiraIssueFields) -> JiraIssue:
        """Create an issue in the configured Jira project."""

    def update_issue(self, key: str, update: JiraIssueUpdate) -> JiraIssue:
        """Update mutable issue fields."""

    def get_transitions(self, key: str) -> tuple[JiraTransition, ...]:
        """Read available workflow transitions for one issue."""

    def transition_issue(self, key: str, target_status: str) -> JiraIssue:
        """Transition one issue to a target workflow status."""

    def create_blocks_link(self, blocker_key: str, blocked_key: str) -> None:
        """Create a Blocks link where blocker_key blocks blocked_key."""

    def get_dependency_links(self, key: str) -> JiraIssueDependencyLinks:
        """Read blocker and blocked issue keys for scheduler eligibility."""

    def list_sprints(self, *, state: str | None = None) -> tuple[JiraSprint, ...]:
        """List sprints from the configured board."""

    def get_sprint(self, sprint_id: str) -> JiraSprint:
        """Read one sprint by id."""

    def get_sprint_issues(self, sprint_id: str) -> tuple[JiraIssue, ...]:
        """Read issue membership for one sprint."""

    def add_issues_to_sprint(self, sprint_id: str, issue_keys: Sequence[str]) -> tuple[str, ...]:
        """Add issues to one sprint and return the sprint issue keys that were requested."""

    def transition_sprint(
        self,
        sprint_id: str,
        target_state: str,
        *,
        name: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> JiraSprint:
        """Transition one sprint lifecycle state using the Jira Agile API."""


class JiraCloudTransport:
    """Small urllib-based Jira Cloud transport."""

    def __init__(self, config: JiraAdapterConfig, *, timeout_seconds: int = 45) -> None:
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
            self.config.normalized_base_url + path,
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
            raise JiraAdapterError(f"Jira request failed: HTTP {exc.code} {raw}") from exc
        except urllib.error.URLError as exc:
            raise JiraAdapterError(f"Jira request failed: {exc.reason}") from exc

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.config.email}:{self.config.api_token}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class JiraCloudProjectIssueAdapter:
    """Jira Cloud implementation for one configured project and board."""

    def __init__(
        self,
        config: JiraAdapterConfig,
        *,
        transport: JiraTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or JiraCloudTransport(config)

    def validate_access(self) -> JiraProjectConfiguration:
        project = self._get_project()
        board = self._get_board()
        _validate_project_board_alignment(self.config, project, board)
        statuses = self._get_statuses()
        priorities = self._get_priorities()
        link_types = self._get_link_types()
        issue_types = project.issue_types or self._get_project_issue_types(project.id)
        return JiraProjectConfiguration(
            project=project,
            board=board,
            statuses=statuses,
            issue_types=issue_types,
            priorities=priorities,
            link_types=link_types,
        )

    def search_issues(self, jql: str, *, fields: Sequence[str] = ()) -> tuple[JiraIssue, ...]:
        query: dict[str, str] = {
            "jql": jql,
            "maxResults": "50",
        }
        if fields:
            query["fields"] = ",".join(fields)
        response = _dict(
            self._transport.request(
                "GET",
                "/rest/api/3/search/jql?" + urllib.parse.urlencode(query),
            )
        )
        return tuple(_issue_from_json(issue) for issue in _list(response.get("issues")))

    def create_issue(self, fields: JiraIssueFields) -> JiraIssue:
        payload: dict[str, object] = {
            "fields": {
                "project": {"key": self.config.project_key},
                "summary": fields.summary,
                "issuetype": {"name": fields.issue_type},
                "labels": list(fields.labels),
            }
        }
        payload_fields = payload["fields"]
        if not isinstance(payload_fields, dict):
            raise JiraAdapterError("Invalid Jira create payload.")
        if fields.description:
            payload_fields["description"] = adf_from_text(fields.description)
        if fields.parent_key:
            payload_fields["parent"] = {"key": fields.parent_key}
        response = _dict(self._transport.request("POST", "/rest/api/3/issue", payload))
        key = str(response.get("key") or "")
        if not key:
            raise JiraAdapterError("Jira create issue response did not include an issue key.")
        return JiraIssue(
            key=key,
            summary=fields.summary,
            issue_type=fields.issue_type,
            labels=fields.labels,
            parent_key=fields.parent_key,
        )

    def update_issue(self, key: str, update: JiraIssueUpdate) -> JiraIssue:
        fields: dict[str, object] = {}
        if update.description is not None:
            fields["description"] = adf_from_text(update.description)
        if update.labels is not None:
            fields["labels"] = list(update.labels)
        if fields:
            self._transport.request("PUT", f"/rest/api/3/issue/{urllib.parse.quote(key)}", {"fields": fields})
        response = self._transport.request(
            "GET",
            f"/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary,status,issuetype,labels,parent",
        )
        return _issue_from_json(response)

    def get_transitions(self, key: str) -> tuple[JiraTransition, ...]:
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/api/3/issue/{urllib.parse.quote(key)}/transitions",
            )
        )
        return tuple(_transition_from_json(item) for item in _list(response.get("transitions")))

    def transition_issue(self, key: str, target_status: str) -> JiraIssue:
        transition = _matching_transition(self.get_transitions(key), target_status)
        if transition is None:
            raise JiraAdapterError(f"No Jira transition available to target status: {target_status}")
        self._transport.request(
            "POST",
            f"/rest/api/3/issue/{urllib.parse.quote(key)}/transitions",
            {"transition": {"id": transition.id}},
        )
        response = self._transport.request(
            "GET",
            f"/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary,status,issuetype,labels,parent",
        )
        return _issue_from_json(response)

    def create_blocks_link(self, blocker_key: str, blocked_key: str) -> None:
        self._transport.request(
            "POST",
            "/rest/api/3/issueLink",
            {
                "type": {"name": self.config.blocks_link_type},
                "inwardIssue": {"key": blocker_key},
                "outwardIssue": {"key": blocked_key},
            },
        )

    def get_dependency_links(self, key: str) -> JiraIssueDependencyLinks:
        response = self._transport.request(
            "GET",
            f"/rest/api/3/issue/{urllib.parse.quote(key)}?fields=issuelinks",
        )
        return _dependency_links_from_issue_json(self.config, key, response)

    def list_sprints(self, *, state: str | None = None) -> tuple[JiraSprint, ...]:
        query: dict[str, str] = {"maxResults": "50"}
        if state:
            query["state"] = state
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/agile/1.0/board/{urllib.parse.quote(self.config.board_id)}/sprint?"
                + urllib.parse.urlencode(query),
            )
        )
        return tuple(_sprint_from_json(item) for item in _list(response.get("values")))

    def get_sprint(self, sprint_id: str) -> JiraSprint:
        response = self._transport.request(
            "GET",
            f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id)}",
        )
        return _sprint_from_json(response)

    def get_sprint_issues(self, sprint_id: str) -> tuple[JiraIssue, ...]:
        query = urllib.parse.urlencode(
            {
                "maxResults": "100",
                "fields": "summary,status,issuetype,labels,parent",
            }
        )
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id)}/issue?{query}",
            )
        )
        return tuple(_issue_from_json(issue) for issue in _list(response.get("issues")))

    def add_issues_to_sprint(self, sprint_id: str, issue_keys: Sequence[str]) -> tuple[str, ...]:
        keys = tuple(key.strip() for key in issue_keys if key and key.strip())
        if not keys:
            return ()
        self._transport.request(
            "POST",
            f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id)}/issue",
            {"issues": list(keys)},
        )
        return keys

    def transition_sprint(
        self,
        sprint_id: str,
        target_state: str,
        *,
        name: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> JiraSprint:
        current = self.get_sprint(sprint_id)
        resolved_name = name or current.name
        if not resolved_name:
            raise JiraAdapterError(
                "Jira sprint transition requires a sprint name; current sprint did not include one."
            )

        payload: dict[str, object] = {"state": target_state, "name": resolved_name}
        if current.goal:
            payload["goal"] = current.goal
        if current.start_date:
            payload["startDate"] = current.start_date
        if current.end_date:
            payload["endDate"] = current.end_date
        if start_date:
            payload["startDate"] = start_date
        if end_date:
            payload["endDate"] = end_date

        try:
            response = self._transport.request(
                "PUT",
                f"/rest/agile/1.0/sprint/{urllib.parse.quote(sprint_id)}",
                payload,
            )
        except JiraAdapterError as exc:
            try:
                reconciled = self.get_sprint(sprint_id)
            except JiraAdapterError as readback_exc:
                raise JiraAdapterError(
                    "Jira sprint transition failed and readback also failed; remote state is unknown."
                ) from readback_exc
            if reconciled.state.casefold() == target_state.casefold():
                return reconciled
            raise JiraAdapterError(
                "Jira sprint transition failed and readback did not confirm target state: "
                f"expected {target_state!r}, read {reconciled.state!r}."
            ) from exc

        sprint = _sprint_from_json(response)
        if sprint.state.casefold() == target_state.casefold():
            return sprint

        try:
            reconciled = self.get_sprint(sprint_id)
        except JiraAdapterError as readback_exc:
            raise JiraAdapterError(
                "Jira sprint transition response was ambiguous and readback failed; remote state is unknown."
            ) from readback_exc
        if reconciled.state.casefold() == target_state.casefold():
            return reconciled
        raise JiraAdapterError(
            "Jira sprint transition response was ambiguous and readback did not confirm target state: "
            f"expected {target_state!r}, response {sprint.state!r}, read {reconciled.state!r}."
        )

    def _get_project(self) -> JiraProjectMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/api/3/project/{urllib.parse.quote(self.config.project_key)}",
            )
        )
        issue_types = tuple(_issue_type_from_json(item) for item in _list(response.get("issueTypes")))
        return JiraProjectMetadata(
            id=str(response.get("id") or ""),
            key=str(response.get("key") or self.config.project_key),
            name=str(response.get("name") or ""),
            issue_types=issue_types,
        )

    def _get_board(self) -> JiraBoardMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/agile/1.0/board/{urllib.parse.quote(self.config.board_id)}",
            )
        )
        location = response.get("location") if isinstance(response.get("location"), dict) else {}
        return JiraBoardMetadata(
            id=str(response.get("id") or self.config.board_id),
            name=str(response.get("name") or ""),
            type=str(response.get("type") or ""),
            project_key=str(location.get("projectKey") or ""),
        )

    def _get_statuses(self) -> tuple[JiraStatus, ...]:
        response = self._transport.request("GET", "/rest/api/3/status")
        return tuple(_status_from_json(item) for item in _list(response))

    def _get_priorities(self) -> tuple[JiraPriority, ...]:
        response = self._transport.request("GET", "/rest/api/3/priority")
        return tuple(_priority_from_json(item) for item in _list(response))

    def _get_link_types(self) -> tuple[JiraLinkType, ...]:
        response = _dict(self._transport.request("GET", "/rest/api/3/issueLinkType"))
        return tuple(_link_type_from_json(item) for item in _list(response.get("issueLinkTypes")))

    def _get_project_issue_types(self, project_id: str) -> tuple[JiraIssueType, ...]:
        if not project_id:
            return ()
        response = self._transport.request(
            "GET",
            "/rest/api/3/issuetype/project?"
            + urllib.parse.urlencode({"projectId": project_id}),
        )
        return tuple(_issue_type_from_json(item) for item in _list(response))


class MockJiraProjectIssueAdapter:
    """In-memory Jira adapter for local workflow tests."""

    def __init__(
        self,
        config: JiraAdapterConfig,
        *,
        project_name: str | None = None,
        board_name: str | None = None,
        statuses: Sequence[str] | None = None,
        issue_types: Sequence[str] | None = None,
        sprints: Sequence[JiraSprint] | None = None,
    ) -> None:
        self.config = config
        self._project_name = project_name or f"{config.project_key} Project"
        self._board_name = board_name or f"{config.project_key} Board"
        self._status_names = tuple(statuses or (config.default_issue_status, "READY TO START", "IN PROGRESS"))
        self._issue_type_names = tuple(
            issue_types
            or (
                config.story_issue_type,
                config.task_issue_type,
                config.bug_issue_type,
                config.test_issue_type,
                config.subtask_issue_type,
            )
        )
        self._issues: dict[str, JiraIssue] = {}
        self._blocks_links: set[tuple[str, str]] = set()
        self._next_number = 1
        self._sprints: dict[str, JiraSprint] = {
            sprint.id: sprint for sprint in (sprints or ())
        }
        self._sprint_issue_keys: dict[str, list[str]] = {sprint.id: [] for sprint in self._sprints.values()}

    def validate_access(self) -> JiraProjectConfiguration:
        issue_types = tuple(
            JiraIssueType(
                id=str(index + 1),
                name=name,
                subtask=name == self.config.subtask_issue_type,
            )
            for index, name in enumerate(self._issue_type_names)
        )
        return JiraProjectConfiguration(
            project=JiraProjectMetadata(
                id=f"mock-{self.config.project_key}",
                key=self.config.project_key,
                name=self._project_name,
                issue_types=issue_types,
            ),
            board=JiraBoardMetadata(
                id=self.config.board_id,
                name=self._board_name,
                type="mock",
                project_key=self.config.project_key,
            ),
            statuses=tuple(
                JiraStatus(id=str(index + 1), name=name, category="mock")
                for index, name in enumerate(self._status_names)
            ),
            issue_types=issue_types,
            priorities=(JiraPriority(id="3", name="Medium"),),
            link_types=(
                JiraLinkType(
                    id="10000",
                    name=self.config.blocks_link_type,
                    inward="is blocked by",
                    outward="blocks",
                ),
            ),
        )

    def search_issues(self, jql: str, *, fields: Sequence[str] = ()) -> tuple[JiraIssue, ...]:
        del fields
        project_token = f"project = {self.config.project_key}".lower()
        if project_token not in jql.lower():
            return ()
        return tuple(sorted(self._issues.values(), key=lambda issue: issue.key))

    def create_issue(self, fields: JiraIssueFields) -> JiraIssue:
        key = f"{self.config.project_key}-{self._next_number}"
        self._next_number += 1
        issue = JiraIssue(
            key=key,
            summary=fields.summary,
            issue_type=fields.issue_type,
            status=self.config.default_issue_status,
            labels=fields.labels,
            parent_key=fields.parent_key,
        )
        self._issues[key] = issue
        return issue

    def update_issue(self, key: str, update: JiraIssueUpdate) -> JiraIssue:
        issue = self._issues.get(key)
        if issue is None:
            raise JiraAdapterError(f"Mock Jira issue does not exist: {key}")
        labels = update.labels if update.labels is not None else issue.labels
        updated = JiraIssue(
            key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            status=issue.status,
            labels=labels,
            parent_key=issue.parent_key,
        )
        self._issues[key] = updated
        return updated

    def get_transitions(self, key: str) -> tuple[JiraTransition, ...]:
        if key not in self._issues:
            raise JiraAdapterError(f"Mock Jira issue does not exist: {key}")
        return tuple(
            JiraTransition(
                id=str(index + 1),
                name=f"Move to {status}",
                to_status=status,
            )
            for index, status in enumerate(self._status_names)
        )

    def transition_issue(self, key: str, target_status: str) -> JiraIssue:
        issue = self._issues.get(key)
        if issue is None:
            raise JiraAdapterError(f"Mock Jira issue does not exist: {key}")
        transition = _matching_transition(self.get_transitions(key), target_status)
        if transition is None:
            raise JiraAdapterError(f"No mock Jira transition available to target status: {target_status}")
        updated = JiraIssue(
            key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            status=transition.to_status,
            labels=issue.labels,
            parent_key=issue.parent_key,
        )
        self._issues[key] = updated
        return updated

    def create_blocks_link(self, blocker_key: str, blocked_key: str) -> None:
        if blocker_key not in self._issues:
            raise JiraAdapterError(f"Mock Jira blocker issue does not exist: {blocker_key}")
        if blocked_key not in self._issues:
            raise JiraAdapterError(f"Mock Jira blocked issue does not exist: {blocked_key}")
        self._blocks_links.add((blocker_key, blocked_key))

    def get_dependency_links(self, key: str) -> JiraIssueDependencyLinks:
        if key not in self._issues:
            raise JiraAdapterError(f"Mock Jira issue does not exist: {key}")
        return JiraIssueDependencyLinks(
            issue_key=key,
            blockers=tuple(blocker for blocker, blocked in sorted(self._blocks_links) if blocked == key),
            blocked=tuple(blocked for blocker, blocked in sorted(self._blocks_links) if blocker == key),
        )

    def list_sprints(self, *, state: str | None = None) -> tuple[JiraSprint, ...]:
        sprints = tuple(self._sprints.values())
        if state is None:
            return tuple(sorted(sprints, key=lambda sprint: sprint.id))
        normalized = {part.strip().casefold() for part in state.split(",") if part.strip()}
        return tuple(
            sprint
            for sprint in sorted(sprints, key=lambda item: item.id)
            if sprint.state.casefold() in normalized
        )

    def get_sprint(self, sprint_id: str) -> JiraSprint:
        sprint = self._sprints.get(sprint_id)
        if sprint is None:
            raise JiraAdapterError(f"Mock Jira sprint does not exist: {sprint_id}")
        return sprint

    def get_sprint_issues(self, sprint_id: str) -> tuple[JiraIssue, ...]:
        sprint = self.get_sprint(sprint_id)
        del sprint
        keys = self._sprint_issue_keys.get(sprint_id, [])
        return tuple(self._issues[key] for key in keys if key in self._issues)

    def add_issues_to_sprint(self, sprint_id: str, issue_keys: Sequence[str]) -> tuple[str, ...]:
        self.get_sprint(sprint_id)
        requested = tuple(key.strip() for key in issue_keys if key and key.strip())
        if not requested:
            return ()
        sprint_keys = self._sprint_issue_keys.setdefault(sprint_id, [])
        for key in requested:
            if key not in self._issues:
                raise JiraAdapterError(f"Mock Jira issue does not exist: {key}")
            if key not in sprint_keys:
                sprint_keys.append(key)
        return requested

    def transition_sprint(
        self,
        sprint_id: str,
        target_state: str,
        *,
        name: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> JiraSprint:
        sprint = self.get_sprint(sprint_id)
        updated = _transition_mock_sprint(
            sprint,
            target_state=target_state,
            name=name,
            start_date=start_date,
            end_date=end_date,
        )
        self._sprints[sprint_id] = updated
        return updated


def jira_config_from_settings(settings: object) -> JiraAdapterConfig:
    """Build adapter config from PlatformSettings or JiraSettings-like objects."""

    jira = getattr(settings, "jira", settings)
    return JiraAdapterConfig(
        base_url=getattr(jira, "base_url"),
        project_key=getattr(jira, "project_key"),
        board_id=str(getattr(jira, "board_id")),
        email=getattr(jira, "email", ""),
        api_token=getattr(jira, "api_token", ""),
    )


def jira_cloud_adapter_from_settings(settings: object) -> JiraCloudProjectIssueAdapter:
    """Create a Jira Cloud adapter from PlatformSettings or JiraSettings."""

    return JiraCloudProjectIssueAdapter(jira_config_from_settings(settings))


def adf_from_text(text: str) -> Mapping[str, object]:
    """Convert plain text into a minimal Atlassian Document Format document."""

    content: list[Mapping[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            content.append({"type": "paragraph"})
        else:
            content.append(
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            )
    return {"type": "doc", "version": 1, "content": content}


def text_from_adf(node: object) -> str:
    """Extract readable text from a small Atlassian Document Format tree."""

    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(text_from_adf(item) for item in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        if node.get("type") == "paragraph":
            return "".join(text_from_adf(item) for item in node.get("content", []))
        return "\n".join(text_from_adf(item) for item in node.get("content", []))
    return ""


def _validate_project_board_alignment(
    config: JiraAdapterConfig,
    project: JiraProjectMetadata,
    board: JiraBoardMetadata,
) -> None:
    configured_project = config.project_key.casefold()
    if project.key and project.key.casefold() != configured_project:
        raise JiraAdapterError(
            "Configured Jira project key does not match returned project: "
            f"{config.project_key} != {project.key}"
        )
    if board.project_key and board.project_key.casefold() != configured_project:
        raise JiraAdapterError(
            "Configured Jira board does not belong to the configured project: "
            f"board {board.id} belongs to {board.project_key}, expected {config.project_key}"
        )


def _issue_from_json(raw: object) -> JiraIssue:
    if not isinstance(raw, dict):
        raise JiraAdapterError("Expected Jira issue JSON object.")
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
    parent = fields.get("parent") if isinstance(fields.get("parent"), dict) else {}
    return JiraIssue(
        key=str(raw.get("key") or ""),
        summary=str(fields.get("summary") or ""),
        issue_type=str(issue_type.get("name") or ""),
        status=str(status.get("name") or ""),
        labels=tuple(str(label) for label in _list(fields.get("labels"))),
        parent_key=str(parent.get("key") or ""),
    )


def _sprint_from_json(raw: object) -> JiraSprint:
    data = _dict(raw)
    origin_board = _dict(data.get("originBoardId"))
    return JiraSprint(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        state=str(data.get("state") or ""),
        goal=str(data.get("goal") or ""),
        start_date=str(data.get("startDate") or ""),
        end_date=str(data.get("endDate") or ""),
        complete_date=str(data.get("completeDate") or ""),
        origin_board_id=str(data.get("originBoardId") or origin_board.get("id") or ""),
    )


def _transition_from_json(raw: object) -> JiraTransition:
    data = _dict(raw)
    target = _dict(data.get("to"))
    return JiraTransition(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        to_status=str(target.get("name") or ""),
    )


def _matching_transition(
    transitions: Sequence[JiraTransition],
    target_status: str,
) -> JiraTransition | None:
    normalized_target = target_status.casefold()
    for transition in transitions:
        if transition.to_status.casefold() == normalized_target:
            return transition
        if transition.name.casefold() == normalized_target:
            return transition
    return None


def _dependency_links_from_issue_json(
    config: JiraAdapterConfig,
    issue_key: str,
    raw: object,
) -> JiraIssueDependencyLinks:
    issue = _dict(raw)
    fields = _dict(issue.get("fields"))
    blockers: list[str] = []
    blocked: list[str] = []
    blocker_issues: list[JiraLinkedIssue] = []
    blocked_issues: list[JiraLinkedIssue] = []
    linked_bugs: list[JiraLinkedIssue] = []
    for link in _list(fields.get("issuelinks")):
        data = _dict(link)
        link_type = _dict(data.get("type"))
        outward_issue = _dict(data.get("outwardIssue"))
        inward_issue = _dict(data.get("inwardIssue"))
        outward = _linked_issue_from_json(outward_issue)
        inward = _linked_issue_from_json(inward_issue)
        if outward and outward.issue_type.casefold() == config.bug_issue_type.casefold():
            linked_bugs.append(outward)
        if inward and inward.issue_type.casefold() == config.bug_issue_type.casefold():
            linked_bugs.append(inward)
        if str(link_type.get("name") or "") != config.blocks_link_type:
            continue
        if inward:
            blockers.append(inward.key)
            blocker_issues.append(inward)
        if outward:
            blocked.append(outward.key)
            blocked_issues.append(outward)
    return JiraIssueDependencyLinks(
        issue_key=issue_key,
        blockers=tuple(blockers),
        blocked=tuple(blocked),
        blocker_issues=tuple(blocker_issues),
        blocked_issues=tuple(blocked_issues),
        linked_bugs=tuple(linked_bugs),
    )


def _linked_issue_from_json(raw: object) -> JiraLinkedIssue | None:
    data = _dict(raw)
    key = str(data.get("key") or "")
    if not key:
        return None
    fields = _dict(data.get("fields"))
    status = _dict(fields.get("status"))
    issue_type = _dict(fields.get("issuetype"))
    return JiraLinkedIssue(
        key=key,
        summary=str(fields.get("summary") or ""),
        issue_type=str(issue_type.get("name") or ""),
        status=str(status.get("name") or ""),
        labels=tuple(str(label) for label in _list(fields.get("labels"))),
    )


def _status_from_json(raw: object) -> JiraStatus:
    data = _dict(raw)
    category = data.get("statusCategory") if isinstance(data.get("statusCategory"), dict) else {}
    return JiraStatus(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        category=str(category.get("name") or ""),
    )


def _issue_type_from_json(raw: object) -> JiraIssueType:
    data = _dict(raw)
    return JiraIssueType(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        subtask=bool(data.get("subtask") or data.get("subTask")),
    )


def _priority_from_json(raw: object) -> JiraPriority:
    data = _dict(raw)
    return JiraPriority(id=str(data.get("id") or ""), name=str(data.get("name") or ""))


def _link_type_from_json(raw: object) -> JiraLinkType:
    data = _dict(raw)
    return JiraLinkType(
        id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        inward=str(data.get("inward") or ""),
        outward=str(data.get("outward") or ""),
    )


def _dict(raw: object) -> Mapping[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def _list(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []


def _transition_mock_sprint(
    sprint: JiraSprint,
    *,
    target_state: str,
    name: str,
    start_date: str,
    end_date: str,
) -> JiraSprint:
    current = sprint.state.casefold()
    target = target_state.casefold()
    if current == target:
        return JiraSprint(
            id=sprint.id,
            name=name or sprint.name,
            state=sprint.state,
            goal=sprint.goal,
            start_date=start_date or sprint.start_date,
            end_date=end_date or sprint.end_date,
            complete_date=sprint.complete_date,
            origin_board_id=sprint.origin_board_id,
        )
    if current == "future" and target == "active":
        resolved_start = start_date or sprint.start_date
        resolved_end = end_date or sprint.end_date
        if not resolved_start or not resolved_end:
            raise JiraAdapterError("Mock Jira sprint requires start_date and end_date before activation.")
        return JiraSprint(
            id=sprint.id,
            name=name or sprint.name,
            state="active",
            goal=sprint.goal,
            start_date=resolved_start,
            end_date=resolved_end,
            complete_date=sprint.complete_date,
            origin_board_id=sprint.origin_board_id,
        )
    if current == "active" and target == "closed":
        return JiraSprint(
            id=sprint.id,
            name=name or sprint.name,
            state="closed",
            goal=sprint.goal,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            complete_date="mock-now",
            origin_board_id=sprint.origin_board_id,
        )
    raise JiraAdapterError(
        f"Unsupported mock Jira sprint transition: {sprint.state} -> {target_state}"
    )
