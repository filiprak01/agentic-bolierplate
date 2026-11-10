from agentic_boilerplate.domain import (
    AgileTestMappingConfig,
    RegressionClassification,
    ReleaseDraftStatus,
    ReleaseDraftWorkItem,
    ReleaseKnownLimitation,
    build_agiletest_mapping_plan,
    build_regression_scope_draft,
    build_release_notes_draft,
    classify_test_issue,
    regression_scope_buckets,
    render_regression_scope_markdown,
    render_release_notes_markdown,
    suggest_release_draft_paths,
)


def test_release_notes_markdown_lists_work_prs_tests_bugs_and_limitations() -> None:
    draft = build_release_notes_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        title="MVP Release Notes",
        generated_at="2026-07-04T14:00:00Z",
        included_items=(
            ReleaseDraftWorkItem(
                key="AGENT-52",
                title="Release Manager scope selection",
                issue_type="Story",
                status="TEST COMPLETED",
                pull_requests=("https://github.com/example-org/agentic-boilerplate/pull/49",),
                test_issue_keys=("AGENT-289",),
                linked_bug_keys=("AGENT-300",),
            ),
        ),
        known_limitations=(
            ReleaseKnownLimitation(
                summary="Manual AgileTest execution update remains outside MVP automation",
                impact="Release Manager must update external execution status manually.",
                workaround="Use the Jira Test Execution evidence comment.",
                linked_issue_key="AGENT-86",
            ),
        ),
    )

    markdown = render_release_notes_markdown(draft)

    assert "# MVP Release Notes" in markdown
    assert "AGENT-52 (Story, TEST COMPLETED): Release Manager scope selection" in markdown
    assert "PR: https://github.com/example-org/agentic-boilerplate/pull/49" in markdown
    assert "Test: AGENT-289" in markdown
    assert "Bug: AGENT-300" in markdown
    assert "Manual AgileTest execution update remains outside MVP automation (AGENT-86)" in markdown


def test_regression_scope_draft_separates_one_time_smoke_release_and_candidates() -> None:
    tests = (
        classify_test_issue(
            test_issue_key="AGENT-302",
            summary="Classification workflow",
            covered_issue_key="AGENT-85",
            classifications=(RegressionClassification.RELEASE_REGRESSION,),
        ),
        classify_test_issue(
            test_issue_key="AGENT-306",
            summary="Visibility workflow",
            covered_issue_key="AGENT-133",
            classifications=(
                RegressionClassification.SMOKE_REGRESSION,
                RegressionClassification.REGRESSION_CANDIDATE,
            ),
        ),
        classify_test_issue(
            test_issue_key="AGENT-400",
            summary="One-time setup validation",
            covered_issue_key="AGENT-55",
            classifications=(RegressionClassification.ONE_TIME_VALIDATION,),
        ),
    )

    draft = build_regression_scope_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        generated_at="2026-07-04T14:00:00Z",
        classified_tests=tests,
        changed_areas=("release-management", "regression-planning"),
        agiletest_mapping_plan=build_agiletest_mapping_plan(
            classified_tests=tests,
            config=AgileTestMappingConfig(enabled=True),
        ),
    )

    buckets = {bucket.classification: bucket.test_issue_keys for bucket in regression_scope_buckets(tests)}

    assert buckets[RegressionClassification.ONE_TIME_VALIDATION] == ("AGENT-400",)
    assert buckets[RegressionClassification.SMOKE_REGRESSION] == ("AGENT-306",)
    assert buckets[RegressionClassification.RELEASE_REGRESSION] == ("AGENT-302",)
    assert buckets[RegressionClassification.REGRESSION_CANDIDATE] == ("AGENT-306",)
    markdown = render_regression_scope_markdown(draft)
    assert "### one-time-validation" in markdown
    assert "### smoke-regression" in markdown
    assert "### release-regression" in markdown
    assert "### regression-candidate" in markdown
    assert "AGENT-302 -> AGENT-85" in markdown


def test_release_draft_paths_are_safe_and_confluence_ready_by_default() -> None:
    paths = suggest_release_draft_paths(root="data/release-drafts", release_key="release-mvp")
    draft = build_release_notes_draft(
        release_key="release-mvp",
        release_version="1.0.0",
        title="MVP Release Notes",
        generated_at="2026-07-04T14:00:00Z",
        included_items=(
            ReleaseDraftWorkItem(
                key="AGENT-55",
                title="Release notes draft workflow",
                issue_type="Story",
                status="IN PROGRESS",
            ),
        ),
    )

    assert paths.release_notes_path == "data/release-drafts/release-mvp/release-notes.md"
    assert paths.regression_scope_path == "data/release-drafts/release-mvp/regression-scope.md"
    assert draft.status is ReleaseDraftStatus.DRAFT
    assert draft.confluence_ready is True
