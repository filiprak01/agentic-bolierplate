from agentic_boilerplate.domain import (
    AgileTestTestExecutionConfig,
    AgileTestTestExecutionIssueFields,
    AgileTestTestExecutionLookupResult,
    AgileTestTestExecutionOperation,
    AgileTestTestExecutionResolutionSource,
    AgileTestTestExecutionUpsertError,
    AgileTestTestExecutionUpsertRequest,
    EvidencePublicationMode,
    build_agiletest_test_execution_upsert_plan,
    execute_agiletest_test_execution_upsert_plan,
)


def test_builds_create_plan_when_no_existing_execution_is_available() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=_base_request(),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    assert plan.operation is AgileTestTestExecutionOperation.CREATE
    assert plan.resolution_source is AgileTestTestExecutionResolutionSource.NEW_EXECUTION
    assert plan.execution_issue_key == "NEW-TEST-EXECUTION"
    assert plan.issue_fields.project_key == "AGENT"
    assert plan.issue_fields.issue_type == "Test execution"
    assert plan.issue_fields.labels == ("agiletest-test-execution",)
    assert [link.target_issue_key for link in plan.publication_request.links] == [
        "NEW-TEST-EXECUTION",
        "AGENT-401",
        "AGENT-402",
    ]


def test_builds_update_plan_from_existing_execution_key() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            **{
                **_base_request().__dict__,
                "existing_execution_key": "AGENT-500",
            }
        ),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    assert plan.operation is AgileTestTestExecutionOperation.UPDATE
    assert plan.resolution_source is AgileTestTestExecutionResolutionSource.EXISTING_EXECUTION_KEY
    assert plan.execution_issue_key == "AGENT-500"
    assert [link.source_issue_key for link in plan.publication_request.links[1:]] == [
        "AGENT-500",
        "AGENT-500",
    ]


def test_lookup_match_is_idempotent_and_uses_configured_project_and_link_types() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            **{
                **_base_request().__dict__,
                "lookup_result": AgileTestTestExecutionLookupResult(
                    matched_execution_keys=("QA-77",),
                    lookup_query='project = QA AND labels = "release-1"',
                ),
            }
        ),
        config=AgileTestTestExecutionConfig(
            project_key="QA",
            issue_type="Execution",
            labels=("release-regression", "agiletest"),
            overview_execution_link_type="Relates",
            overview_execution_relationship="relates to",
            execution_test_case_link_type="Tests",
            execution_test_case_relationship="tests",
        ),
    )

    assert plan.operation is AgileTestTestExecutionOperation.UPDATE
    assert plan.resolution_source is AgileTestTestExecutionResolutionSource.LOOKUP_MATCH
    assert plan.execution_issue_key == "QA-77"
    assert plan.lookup_query == 'project = QA AND labels = "release-1"'
    assert plan.issue_fields == AgileTestTestExecutionIssueFields(
        project_key="QA",
        issue_type="Execution",
        summary="release-mvp mvp-sprint-10 Test Execution",
        description=(
            "Release key: release-mvp\n"
            "Sprint label: mvp-sprint-10\n"
            "Regression overview: AGENT-239\n"
            "Evidence path: data/agent-logs/REGRESSION-S10/regression-evidence.md\n\n"
            "Included Test Cases:\n"
            "- AGENT-401\n"
            "- AGENT-402"
        ),
        labels=("release-regression", "agiletest"),
    )
    assert plan.publication_request.links[0].link_type == "Relates"
    assert plan.publication_request.links[1].link_type == "Tests"


def test_lookup_with_multiple_matches_is_rejected() -> None:
    try:
        build_agiletest_test_execution_upsert_plan(
            request=AgileTestTestExecutionUpsertRequest(
                **{
                    **_base_request().__dict__,
                    "lookup_result": AgileTestTestExecutionLookupResult(
                        matched_execution_keys=("AGENT-500", "AGENT-501"),
                    ),
                }
            ),
            config=AgileTestTestExecutionConfig(project_key="AGENT"),
        )
    except AgileTestTestExecutionUpsertError as error:
        assert "at most one Test Execution" in str(error)
    else:
        raise AssertionError("Expected ambiguous lookup result to fail")


def test_dry_run_execution_returns_plan_without_adapter() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=_base_request(),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    result = execute_agiletest_test_execution_upsert_plan(plan)

    assert result.succeeded
    assert result.mode is EvidencePublicationMode.DRY_RUN
    assert result.execution_issue_key == "NEW-TEST-EXECUTION"
    assert result.publication_request == plan.publication_request


def test_live_create_execution_resolves_placeholder_links() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            **{
                **_base_request().__dict__,
                "mode": EvidencePublicationMode.LIVE,
            }
        ),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    adapter = _RecordingAdapter(created_key="AGENT-600")
    result = execute_agiletest_test_execution_upsert_plan(plan, adapter=adapter)

    assert result.succeeded
    assert adapter.created == (plan.issue_fields,)
    assert result.execution_issue_key == "AGENT-600"
    assert [(link.source_issue_key, link.target_issue_key) for link in result.publication_request.links] == [
        ("AGENT-239", "AGENT-600"),
        ("AGENT-600", "AGENT-401"),
        ("AGENT-600", "AGENT-402"),
    ]


def test_live_update_failure_keeps_evidence_path_for_recovery() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            **{
                **_base_request().__dict__,
                "mode": EvidencePublicationMode.LIVE,
                "existing_execution_key": "AGENT-500",
            }
        ),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    adapter = _RecordingAdapter(fail_update=True)
    result = execute_agiletest_test_execution_upsert_plan(plan, adapter=adapter)

    assert not result.succeeded
    assert result.failures[0].evidence_path == "data/agent-logs/REGRESSION-S10/regression-evidence.md"
    assert result.failures[0].execution_issue_key == "AGENT-500"
    assert "update failed" in result.failures[0].message


def test_live_execution_requires_adapter() -> None:
    plan = build_agiletest_test_execution_upsert_plan(
        request=AgileTestTestExecutionUpsertRequest(
            **{
                **_base_request().__dict__,
                "mode": EvidencePublicationMode.LIVE,
            }
        ),
        config=AgileTestTestExecutionConfig(project_key="AGENT"),
    )

    try:
        execute_agiletest_test_execution_upsert_plan(plan)
    except AgileTestTestExecutionUpsertError as error:
        assert "adapter is required" in str(error)
    else:
        raise AssertionError("Expected live execution without adapter to fail")


def _base_request() -> AgileTestTestExecutionUpsertRequest:
    return AgileTestTestExecutionUpsertRequest(
        release_key="release-mvp",
        sprint_label="mvp-sprint-10",
        regression_overview_key="AGENT-239",
        evidence_path="data/agent-logs/REGRESSION-S10/regression-evidence.md",
        test_case_keys=("AGENT-401", "AGENT-402"),
    )


class _RecordingAdapter:
    def __init__(self, *, created_key: str = "", fail_update: bool = False) -> None:
        self.created_key = created_key
        self.fail_update = fail_update
        self.created: tuple[AgileTestTestExecutionIssueFields, ...] = ()
        self.updated: tuple[tuple[str, AgileTestTestExecutionIssueFields], ...] = ()

    def create_test_execution(self, fields: AgileTestTestExecutionIssueFields) -> str:
        self.created = (*self.created, fields)
        return self.created_key or "AGENT-NEW"

    def update_test_execution(self, issue_key: str, fields: AgileTestTestExecutionIssueFields) -> None:
        if self.fail_update:
            raise RuntimeError("update failed because issue is locked")
        self.updated = (*self.updated, (issue_key, fields))
