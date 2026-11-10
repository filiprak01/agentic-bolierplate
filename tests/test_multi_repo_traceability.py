from agentic_boilerplate.domain import (
    RepositoryTraceabilityRole,
    RepositoryTraceabilityTarget,
    RepositoryWorkTrace,
    TraceabilityIssueKind,
    build_jira_development_panel_warnings,
    render_expected_repository_section,
    render_manual_multi_repo_pr_link_comment,
    validate_multi_repo_traceability,
)


def test_multi_repo_traceability_passes_with_visible_project_and_process_prs() -> None:
    decision = validate_multi_repo_traceability(
        jira_issue_key="AP-29",
        traces=(
            _trace(
                RepositoryTraceabilityRole.TARGET_IMPLEMENTATION,
                repository="example-org/ap-airline",
                branch_name="feature/AP-29-booking-api",
                pull_request_title="AP-29 Booking API",
                pull_request_body="AP-29 target-implementation change.",
            ),
            _trace(
                RepositoryTraceabilityRole.BOILERPLATE_PROCESS,
                repository="example-org/agentic-boilerplate",
                branch_name="feature/AP-29-process-linking",
                pull_request_title="AP-29 Process linking",
                pull_request_body="AP-29 boilerplate-process change.",
                process_change_reason="AP-29 required a reusable process fix.",
            ),
        ),
        multi_repo_reason="AP-29 needs target code plus reusable boilerplate process support.",
    )

    assert decision.passed is True
    assert decision.issues == ()


def test_multi_repo_traceability_blocks_missing_visible_lineage() -> None:
    decision = validate_multi_repo_traceability(
        jira_issue_key="AP-29",
        traces=(
            _trace(
                RepositoryTraceabilityRole.TARGET_IMPLEMENTATION,
                repository="example-org/ap-airline",
                branch_name="feature/booking-api",
                commit_messages=("implement booking API",),
                pull_request_title="Booking API",
                pull_request_body="target-implementation change.",
            ),
        ),
    )

    kinds = {issue.kind for issue in decision.issues}

    assert decision.passed is False
    assert TraceabilityIssueKind.MISSING_BRANCH_JIRA_KEY in kinds
    assert TraceabilityIssueKind.MISSING_COMMIT_JIRA_KEY in kinds
    assert TraceabilityIssueKind.MISSING_PR_TITLE_JIRA_KEY in kinds
    assert TraceabilityIssueKind.MISSING_PR_BODY_JIRA_KEY in kinds


def test_multi_repo_traceability_requires_reason_for_multi_repo_work() -> None:
    decision = validate_multi_repo_traceability(
        jira_issue_key="AP-29",
        traces=(
            _trace(RepositoryTraceabilityRole.TARGET_IMPLEMENTATION, repository="example-org/ap-airline"),
            _trace(
                RepositoryTraceabilityRole.BOILERPLATE_PROCESS,
                repository="example-org/agentic-boilerplate",
                process_change_reason="AP-29 required a reusable process fix.",
            ),
        ),
    )

    assert TraceabilityIssueKind.MISSING_MULTI_REPO_REASON in {issue.kind for issue in decision.issues}


def test_multi_repo_traceability_requires_at_least_one_commit_message() -> None:
    decision = validate_multi_repo_traceability(
        jira_issue_key="AP-29",
        traces=(
            _trace(
                RepositoryTraceabilityRole.TARGET_IMPLEMENTATION,
                repository="example-org/ap-airline",
                commit_messages=(),
            ),
        ),
    )

    assert TraceabilityIssueKind.MISSING_COMMIT_JIRA_KEY in {issue.kind for issue in decision.issues}


def test_multi_repo_traceability_requires_manual_jira_link_when_panel_not_expected() -> None:
    decision = validate_multi_repo_traceability(
        jira_issue_key="AP-29",
        traces=(
            _trace(
                RepositoryTraceabilityRole.DOCUMENTATION,
                repository="example-org/ap-docs",
                jira_development_panel_expected=False,
                pull_request_url="",
            ),
        ),
    )

    assert decision.passed is False
    assert decision.warnings
    assert TraceabilityIssueKind.MISSING_MANUAL_JIRA_PR_LINK in {issue.kind for issue in decision.issues}


def test_multi_repo_traceability_renders_story_section_warnings_and_fallback_comment() -> None:
    target = RepositoryTraceabilityTarget(
        role=RepositoryTraceabilityRole.AUTOMATION,
        repository="example-org/ap-automation",
        default_branch="main",
        jira_development_panel_expected=False,
    )
    trace = RepositoryWorkTrace(
        target=target,
        branch_name="feature/AP-29-regression",
        commit_messages=("AP-29 add regression coverage",),
        pull_request_title="AP-29 Regression coverage",
        pull_request_body="AP-29 automation repo coverage.",
        pull_request_url="https://github.com/example-org/ap-automation/pull/7",
    )

    section = render_expected_repository_section((target,))
    warnings = build_jira_development_panel_warnings((target,))
    comment = render_manual_multi_repo_pr_link_comment(jira_issue_key="AP-29", trace=trace)

    assert "Expected Repositories:" in section
    assert "automation: example-org/ap-automation" in section
    assert warnings == ("automation: example-org/ap-automation will require explicit Jira PR links.",)
    assert "Manual repository PR link for AP-29." in comment
    assert "PR: https://github.com/example-org/ap-automation/pull/7" in comment


def _trace(
    role: RepositoryTraceabilityRole,
    *,
    repository: str,
    branch_name: str = "feature/AP-29-example",
    commit_messages: tuple[str, ...] = ("AP-29 example change",),
    pull_request_title: str = "AP-29 Example change",
    pull_request_body: str = "AP-29 example repository lane.",
    pull_request_url: str = "https://github.example/pull/1",
    jira_development_panel_expected: bool = True,
    process_change_reason: str = "",
) -> RepositoryWorkTrace:
    return RepositoryWorkTrace(
        target=RepositoryTraceabilityTarget(
            role=role,
            repository=repository,
            jira_development_panel_expected=jira_development_panel_expected,
        ),
        branch_name=branch_name,
        commit_messages=commit_messages,
        pull_request_title=pull_request_title,
        pull_request_body=pull_request_body,
        pull_request_url=pull_request_url,
        process_change_reason=process_change_reason,
    )
