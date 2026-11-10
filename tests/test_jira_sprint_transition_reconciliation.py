from agentic_boilerplate.integrations import (
    JiraAdapterConfig,
    JiraAdapterError,
    JiraCloudProjectIssueAdapter,
)


class SprintTransitionTransport:
    def __init__(
        self,
        *,
        current_sprint: dict[str, object] | None = None,
        put_response: object | None = None,
        readback_after_put: dict[str, object] | None = None,
        put_error: str = "",
    ) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.current_sprint = current_sprint or {
            "id": 44,
            "name": "Sprint 44",
            "state": "active",
            "goal": "Ship hardening",
            "startDate": "2026-07-01T09:00:00.000Z",
            "endDate": "2026-07-07T18:00:00.000Z",
            "originBoardId": 987,
        }
        self.put_response = put_response
        self.readback_after_put = readback_after_put
        self.put_error = put_error

    def request(self, method: str, path: str, payload: object = None) -> object:
        self.calls.append((method, path, payload))
        if path == "/rest/agile/1.0/sprint/44" and method == "GET":
            return dict(self.current_sprint)
        if path == "/rest/agile/1.0/sprint/44" and method == "PUT":
            if self.put_error:
                if self.readback_after_put is not None:
                    self.current_sprint = dict(self.readback_after_put)
                raise JiraAdapterError(self.put_error)
            response = self.put_response
            if response is None:
                response = {
                    **self.current_sprint,
                    **(payload if isinstance(payload, dict) else {}),
                }
                if isinstance(payload, dict) and payload.get("state") == "closed":
                    response["completeDate"] = "2026-07-07T18:30:00.000Z"
            if self.readback_after_put is not None:
                self.current_sprint = dict(self.readback_after_put)
            elif isinstance(response, dict):
                self.current_sprint = dict(response)
            return response
        raise AssertionError(f"Unexpected request: {method} {path}")


def adapter_with(
    transport: SprintTransitionTransport,
) -> JiraCloudProjectIssueAdapter:
    return JiraCloudProjectIssueAdapter(
        JiraAdapterConfig(
            base_url="https://example.atlassian.net",
            project_key="CUSTOM",
            board_id="987",
        ),
        transport=transport,
    )


def put_payload(transport: SprintTransitionTransport) -> object:
    return next(payload for method, _path, payload in transport.calls if method == "PUT")


def test_transition_sprint_preserves_required_current_fields_when_state_only() -> None:
    transport = SprintTransitionTransport()

    closed = adapter_with(transport).transition_sprint("44", "closed")

    assert put_payload(transport) == {
        "state": "closed",
        "name": "Sprint 44",
        "goal": "Ship hardening",
        "startDate": "2026-07-01T09:00:00.000Z",
        "endDate": "2026-07-07T18:00:00.000Z",
    }
    assert closed.state == "closed"
    assert closed.goal == "Ship hardening"
    assert closed.start_date == "2026-07-01T09:00:00.000Z"
    assert closed.end_date == "2026-07-07T18:00:00.000Z"


def test_transition_sprint_preserves_metadata_when_only_name_is_overridden() -> None:
    transport = SprintTransitionTransport()

    active = adapter_with(transport).transition_sprint(
        "44",
        "active",
        name="Sprint 44 adjusted",
    )

    assert put_payload(transport) == {
        "state": "active",
        "name": "Sprint 44 adjusted",
        "goal": "Ship hardening",
        "startDate": "2026-07-01T09:00:00.000Z",
        "endDate": "2026-07-07T18:00:00.000Z",
    }
    assert active.name == "Sprint 44 adjusted"
    assert active.goal == "Ship hardening"
    assert active.start_date == "2026-07-01T09:00:00.000Z"
    assert active.end_date == "2026-07-07T18:00:00.000Z"


def test_transition_sprint_honors_explicit_supported_overrides() -> None:
    transport = SprintTransitionTransport()

    active = adapter_with(transport).transition_sprint(
        "44",
        "active",
        name="Sprint 44 adjusted",
        start_date="2026-07-02T09:00:00.000Z",
        end_date="2026-07-08T18:00:00.000Z",
    )

    payload = put_payload(transport)
    assert payload == {
        "state": "active",
        "name": "Sprint 44 adjusted",
        "goal": "Ship hardening",
        "startDate": "2026-07-02T09:00:00.000Z",
        "endDate": "2026-07-08T18:00:00.000Z",
    }
    assert active.name == "Sprint 44 adjusted"
    assert active.goal == "Ship hardening"
    assert active.start_date == "2026-07-02T09:00:00.000Z"
    assert active.end_date == "2026-07-08T18:00:00.000Z"


def test_transition_sprint_reconciles_transition_applied_before_error() -> None:
    transport = SprintTransitionTransport(
        put_error="HTTP 504 after transition",
        readback_after_put={
            "id": 44,
            "name": "Sprint 44",
            "state": "closed",
            "goal": "Ship hardening",
            "startDate": "2026-07-01T09:00:00.000Z",
            "endDate": "2026-07-07T18:00:00.000Z",
            "completeDate": "2026-07-07T18:30:00.000Z",
            "originBoardId": 987,
        },
    )

    closed = adapter_with(transport).transition_sprint("44", "closed")

    assert closed.state == "closed"
    assert [call[0] for call in transport.calls] == ["GET", "PUT", "GET"]


def test_transition_sprint_fails_when_rejection_readback_not_target() -> None:
    transport = SprintTransitionTransport(
        put_error="HTTP 400 name required",
        readback_after_put={
            "id": 44,
            "name": "Sprint 44",
            "state": "active",
            "goal": "Ship hardening",
            "startDate": "2026-07-01T09:00:00.000Z",
            "endDate": "2026-07-07T18:00:00.000Z",
            "originBoardId": 987,
        },
    )

    try:
        adapter_with(transport).transition_sprint("44", "closed")
    except JiraAdapterError as exc:
        assert "readback did not confirm target state" in str(exc)
    else:
        raise AssertionError("Expected sprint transition rejection to fail closed.")


def test_transition_sprint_fails_when_ambiguous_response_readback_not_target() -> None:
    transport = SprintTransitionTransport(
        put_response={},
        readback_after_put={
            "id": 44,
            "name": "Sprint 44",
            "state": "active",
            "goal": "Ship hardening",
            "startDate": "2026-07-01T09:00:00.000Z",
            "endDate": "2026-07-07T18:00:00.000Z",
            "originBoardId": 987,
        },
    )

    try:
        adapter_with(transport).transition_sprint("44", "closed")
    except JiraAdapterError as exc:
        assert "readback did not confirm target state" in str(exc)
    else:
        raise AssertionError("Expected ambiguous sprint transition to fail closed.")


def test_transition_sprint_requires_name_before_put() -> None:
    transport = SprintTransitionTransport(
        current_sprint={
            "id": 44,
            "name": "",
            "state": "active",
            "goal": "Ship hardening",
            "startDate": "2026-07-01T09:00:00.000Z",
            "endDate": "2026-07-07T18:00:00.000Z",
            "originBoardId": 987,
        }
    )

    try:
        adapter_with(transport).transition_sprint("44", "closed")
    except JiraAdapterError as exc:
        assert "requires a sprint name" in str(exc)
    else:
        raise AssertionError("Expected sprint transition without a name to fail.")
    assert all(method != "PUT" for method, _path, _payload in transport.calls)
