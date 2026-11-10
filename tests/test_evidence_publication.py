from agentic_boilerplate.domain import (
    EvidencePublicationActionType,
    EvidencePublicationError,
    EvidencePublicationMode,
    EvidenceCommentPlan,
    EvidenceAttachmentPlan,
    EvidenceLinkPlan,
    build_agiletest_evidence_link_plans,
    build_evidence_attachment_plan,
    build_evidence_comment_plan,
    build_evidence_publication_request,
    evidence_publication_failure,
    execute_evidence_publication_request,
)


def test_comment_plan_references_local_evidence_file() -> None:
    plan = build_evidence_comment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        result_summary="Tester validation PASSED",
        details="Focused and full suites passed.",
    )

    assert plan.issue_key == "AGENT-136"
    assert "Evidence file: data/agent-logs/AGENT-136/test-evidence.md" in plan.body
    assert "Focused and full suites passed." in plan.body


def test_attachment_plan_supports_reattaching_updated_evidence() -> None:
    plan = build_evidence_attachment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        filename="test-evidence.md",
        replace_existing=True,
    )

    assert plan.filename == "test-evidence.md"
    assert plan.replace_existing is True


def test_agiletest_link_plans_connect_overview_execution_and_test_cases() -> None:
    plans = build_agiletest_evidence_link_plans(
        overview_task_key="AGENT-239",
        test_execution_key="AGENT-330",
        test_case_keys=("AGENT-322", "AGENT-326"),
    )

    assert [(plan.source_issue_key, plan.target_issue_key) for plan in plans] == [
        ("AGENT-239", "AGENT-330"),
        ("AGENT-330", "AGENT-322"),
        ("AGENT-330", "AGENT-326"),
    ]
    assert {plan.link_type for plan in plans} == {"AgileTest"}


def test_publication_request_requires_at_least_one_action() -> None:
    try:
        build_evidence_publication_request(
            evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
            mode=EvidencePublicationMode.DRY_RUN,
        )
    except EvidencePublicationError as error:
        assert "at least one publication action is required" in str(error)
    else:
        raise AssertionError("Expected request without actions to fail")


def test_failure_record_keeps_evidence_path_for_recovery() -> None:
    failure = evidence_publication_failure(
        action_type=EvidencePublicationActionType.ATTACHMENT,
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        message="Jira attachment permission denied",
    )

    assert failure.evidence_path == "data/agent-logs/AGENT-136/test-evidence.md"
    assert failure.message == "Jira attachment permission denied"


def test_publication_request_accepts_comments_attachments_and_links() -> None:
    comment = build_evidence_comment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        result_summary="Tester validation PASSED",
    )
    attachment = build_evidence_attachment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
    )
    links = build_agiletest_evidence_link_plans(
        overview_task_key="AGENT-239",
        test_execution_key="AGENT-330",
        test_case_keys=("AGENT-326",),
    )

    request = build_evidence_publication_request(
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        mode=EvidencePublicationMode.DRY_RUN,
        comments=(comment,),
        attachments=(attachment,),
        links=links,
    )

    assert request.mode is EvidencePublicationMode.DRY_RUN
    assert len(request.comments) == 1
    assert len(request.attachments) == 1
    assert len(request.links) == 2


def test_dry_run_records_planned_actions_without_publisher() -> None:
    comment = build_evidence_comment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        result_summary="Tester validation PASSED",
    )
    links = build_agiletest_evidence_link_plans(
        overview_task_key="AGENT-239",
        test_execution_key="AGENT-330",
        test_case_keys=("AGENT-326",),
    )
    request = build_evidence_publication_request(
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        mode=EvidencePublicationMode.DRY_RUN,
        comments=(comment,),
        links=links,
    )

    result = execute_evidence_publication_request(request)

    assert result.succeeded
    assert [action.action_type.value for action in result.actions] == ["comment", "link", "link"]


def test_live_publication_uses_mock_publisher() -> None:
    publisher = _RecordingPublisher()
    comment = build_evidence_comment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        result_summary="Tester validation PASSED",
    )
    attachment = build_evidence_attachment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
    )
    links = build_agiletest_evidence_link_plans(
        overview_task_key="AGENT-239",
        test_execution_key="AGENT-330",
        test_case_keys=("AGENT-326",),
    )
    request = build_evidence_publication_request(
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        mode=EvidencePublicationMode.LIVE,
        comments=(comment,),
        attachments=(attachment,),
        links=links,
    )

    result = execute_evidence_publication_request(request, publisher=publisher)

    assert result.succeeded
    assert publisher.comments == (comment,)
    assert publisher.attachments == (attachment,)
    assert publisher.links == links


def test_live_publication_records_attachment_failure_with_evidence_path() -> None:
    publisher = _RecordingPublisher(fail_attachments=True)
    attachment = build_evidence_attachment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
    )
    request = build_evidence_publication_request(
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        mode=EvidencePublicationMode.LIVE,
        attachments=(attachment,),
    )

    result = execute_evidence_publication_request(request, publisher=publisher)

    assert not result.succeeded
    assert result.failures[0].action_type is EvidencePublicationActionType.ATTACHMENT
    assert result.failures[0].evidence_path == "data/agent-logs/AGENT-136/test-evidence.md"
    assert "permission denied" in result.failures[0].message


def test_live_publication_requires_publisher() -> None:
    comment = build_evidence_comment_plan(
        issue_key="AGENT-136",
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        result_summary="Tester validation PASSED",
    )
    request = build_evidence_publication_request(
        evidence_path="data/agent-logs/AGENT-136/test-evidence.md",
        mode=EvidencePublicationMode.LIVE,
        comments=(comment,),
    )

    try:
        execute_evidence_publication_request(request)
    except EvidencePublicationError as error:
        assert "publisher is required" in str(error)
    else:
        raise AssertionError("Expected live execution without publisher to fail")


class _RecordingPublisher:
    def __init__(self, *, fail_attachments: bool = False) -> None:
        self.fail_attachments = fail_attachments
        self.comments: tuple[EvidenceCommentPlan, ...] = ()
        self.attachments: tuple[EvidenceAttachmentPlan, ...] = ()
        self.links: tuple[EvidenceLinkPlan, ...] = ()

    def add_comment(self, plan: EvidenceCommentPlan) -> None:
        self.comments = (*self.comments, plan)

    def attach_evidence(self, plan: EvidenceAttachmentPlan) -> None:
        if self.fail_attachments:
            raise RuntimeError("permission denied for attachment")
        self.attachments = (*self.attachments, plan)

    def link_issues(self, plan: EvidenceLinkPlan) -> None:
        self.links = (*self.links, plan)
