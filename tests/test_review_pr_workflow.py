from agentic_boilerplate.domain import (
    PullRequestReviewInput,
    PullRequestReviewWorkflowError,
    ReasoningLevel,
    ReviewApprovalPublicationMode,
    ReviewDecision,
    ReviewExpansionReason,
    ReviewFindingKind,
    ReviewFindingSeverity,
    ReviewModelRouting,
    ReviewScopeMode,
    StackedPullRequestReviewContext,
    StackedReviewMergeStrategy,
    build_review_approval_publication_status,
    build_initial_review_record,
    decide_stacked_pull_request_review,
    decide_pull_request_review,
    jira_status_after_review_merge,
    plan_review_scope,
    render_review_approval_publication_status,
    render_review_merged_comment,
    render_stacked_pull_request_review_comment,
    require_valid_pull_request_review_input,
    stacked_review_layer_record_to_dict,
)
from agentic_boilerplate.integrations import (
    GitHubAdapterConfig,
    GitHubPullRequestFields,
    GitHubPullRequestMergeResult,
    MockGitHubRepositoryAdapter,
)


def test_review_input_requires_diff_and_acceptance_context() -> None:
    review_input = PullRequestReviewInput(
        **{
            **_review_input().__dict__,
            "changed_files": (),
        }
    )

    try:
        require_valid_pull_request_review_input(review_input)
    except PullRequestReviewWorkflowError as exc:
        assert "changed_files" in str(exc)
    else:
        raise AssertionError("Expected missing changed files to fail review input validation.")


def test_review_scope_defaults_to_diff_first() -> None:
    scope = plan_review_scope(_review_input())

    assert scope.mode == ReviewScopeMode.DIFF_FIRST
    assert scope.changed_files == ("src/agentic_boilerplate/domain/review_record.py",)
    assert scope.related_tests == ("tests/test_review_record.py",)
    assert scope.expanded_context_paths == ()


def test_review_scope_expands_only_with_reason() -> None:
    review_input = PullRequestReviewInput(
        **{
            **_review_input().__dict__,
            "expanded_context_paths": ("src/agentic_boilerplate/integrations/github.py",),
            "expansion_reasons": (ReviewExpansionReason.SHARED_CONTRACT,),
        }
    )

    scope = plan_review_scope(review_input)

    assert scope.mode == ReviewScopeMode.EXPANDED_CONTEXT
    assert scope.expansion_reason == "shared-contract"
    assert scope.expanded_context_paths == ("src/agentic_boilerplate/integrations/github.py",)


def test_initial_review_record_marks_conflicts_as_review_findings_not_bugs() -> None:
    record = build_initial_review_record(
        PullRequestReviewInput(
            **{
                **_review_input().__dict__,
                "detected_conflicts": ("Merge conflict in src/app.py",),
            }
        ),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )

    assert record.findings[0].kind == ReviewFindingKind.CONFLICT
    assert record.findings[0].severity == ReviewFindingSeverity.BLOCKING
    assert "bug" not in record.findings[0].__dict__


def test_initial_review_record_adds_missing_jira_pr_visibility_finding() -> None:
    record = build_initial_review_record(
        PullRequestReviewInput(
            **{
                **_review_input().__dict__,
                "existing_jira_pr_link_visible": False,
            }
        ),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )

    assert record.findings[0].id == "jira-pr-link-001"
    assert "missing visible pull request link" in record.findings[0].title
    assert "could not confirm" in record.findings[0].description


def test_initial_review_record_flags_unrelated_staged_files() -> None:
    record = build_initial_review_record(
        PullRequestReviewInput(
            **{
                **_review_input().__dict__,
                "unrelated_staged_files": ("docs/unrelated.md", ".env.example"),
            }
        ),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )

    assert record.findings[0].id == "staged-scope-001"
    assert record.findings[0].severity == ReviewFindingSeverity.HIGH
    assert "docs/unrelated.md" in record.findings[0].description


def test_review_decision_requests_changes_when_open_findings_exist() -> None:
    record = build_initial_review_record(
        PullRequestReviewInput(
            **{
                **_review_input().__dict__,
                "existing_jira_pr_link_visible": False,
            }
        ),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )

    result = decide_pull_request_review(record, merge_commit_title="Merge pull request #48")

    assert result.ready_to_merge is False
    assert result.merge_fields is None
    assert result.review_record.final_decision == ReviewDecision.CHANGES_REQUESTED
    assert "changes requested" in result.jira_comment


def test_clean_review_is_merge_ready_and_targets_dev_completed_for_tester_handoff() -> None:
    record = build_initial_review_record(
        _review_input(),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )

    result = decide_pull_request_review(record, merge_commit_title="Merge pull request #48")

    assert result.ready_to_merge is True
    assert result.review_record.final_decision == ReviewDecision.APPROVED
    assert result.merge_fields is not None
    assert result.merge_fields.number == 48
    assert result.jira_status_after_merge == "DEV COMPLETED"
    assert jira_status_after_review_merge() == "DEV COMPLETED"


def test_clean_review_merge_can_use_mock_github_adapter_and_render_jira_comment() -> None:
    adapter = MockGitHubRepositoryAdapter(
        GitHubAdapterConfig(repository="ExampleOrg/example-repo"),
        default_branch_sha="a" * 40,
    )
    adapter.create_branch("feature/AGENT-48-review-agent-pr-workflow", "main")
    pull_request = adapter.create_pull_request(
        GitHubPullRequestFields(
            title="AGENT-48 review workflow",
            head="feature/AGENT-48-review-agent-pr-workflow",
            base="main",
            draft=False,
        )
    )
    record = build_initial_review_record(
        PullRequestReviewInput(
            **{
                **_review_input().__dict__,
                "pull_request_number": pull_request.number,
            }
        ),
        _routing(),
        created_at="2026-07-03T17:00:00Z",
        updated_at="2026-07-03T17:00:00Z",
    )
    result = decide_pull_request_review(record, merge_commit_title="Merge pull request #48")

    merge_result = adapter.merge_pull_request(result.merge_fields)
    comment = render_review_merged_comment(result.review_record, merge_result)

    assert isinstance(merge_result, GitHubPullRequestMergeResult)
    assert "Next Jira status: DEV COMPLETED" in comment
    assert adapter.get_pull_request(pull_request.number).state == "closed"


def test_review_approval_publication_records_formal_review_success() -> None:
    status = build_review_approval_publication_status(
        jira_issue_key="AGENT-48",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/48",
        review_record_id="review-AGENT-48-PR-48",
        formal_review_created=True,
        fallback_comment_created=False,
    )

    rendered = render_review_approval_publication_status(status)

    assert status.mode is ReviewApprovalPublicationMode.FORMAL_REVIEW
    assert status.published is True
    assert "formal GitHub approval review was created" in rendered


def test_review_approval_publication_records_422_comment_fallback() -> None:
    status = build_review_approval_publication_status(
        jira_issue_key="AGENT-48",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/48",
        review_record_id="review-AGENT-48-PR-48",
        formal_review_created=False,
        fallback_comment_created=True,
        provider_status_code=422,
        provider_message="Review cannot be submitted.",
    )

    rendered = render_review_approval_publication_status(status)

    assert status.mode is ReviewApprovalPublicationMode.COMMENT_FALLBACK
    assert status.published is True
    assert "unprocessable" in status.diagnostic_summary
    assert "Fallback comment created: yes" in rendered
    assert "Provider status code: 422" in rendered


def test_review_approval_publication_records_failed_publication() -> None:
    status = build_review_approval_publication_status(
        jira_issue_key="AGENT-48",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/48",
        review_record_id="review-AGENT-48-PR-48",
        formal_review_created=False,
        fallback_comment_created=False,
        provider_status_code=401,
    )

    assert status.mode is ReviewApprovalPublicationMode.FAILED
    assert status.published is False
    assert "authentication" in render_review_approval_publication_status(status)


def test_stacked_review_requires_metadata_jira_base_checks_and_lower_approval() -> None:
    decision = decide_stacked_pull_request_review(
        StackedPullRequestReviewContext(
            **{
                **_stacked_review_context().__dict__,
                "stack_metadata_present": False,
                "jira_pr_link_visible": False,
                "base_branch": "main",
                "checks_passed": False,
                "required_lower_layer_approved": False,
            }
        )
    )

    blockers = "\n".join(decision.approval_blockers)

    assert decision.approval_ready is False
    assert decision.merge_ready is False
    assert "Stack metadata is missing" in blockers
    assert "visible pull request link" in blockers
    assert "configured stack base branch" in blockers
    assert "checks are failing" in blockers
    assert "lower-layer approval is missing" in blockers


def test_stacked_review_allows_early_upper_layer_review_but_blocks_bottom_up_merge() -> None:
    decision = decide_stacked_pull_request_review(
        StackedPullRequestReviewContext(
            **{
                **_stacked_review_context().__dict__,
                "required_lower_layer_approved": True,
                "required_lower_layer_merged": False,
            }
        )
    )

    assert decision.approval_ready is True
    assert decision.merge_ready is False
    assert decision.merge_strategy is StackedReviewMergeStrategy.BOTTOM_UP
    assert decision.merge_blockers == ("Lower stack layer must merge before this layer can merge.",)


def test_stacked_review_marks_upper_layer_stale_when_lower_layer_changed() -> None:
    decision = decide_stacked_pull_request_review(
        StackedPullRequestReviewContext(
            **{
                **_stacked_review_context().__dict__,
                "lower_layer_recorded_head_sha": "old-parent",
                "lower_layer_current_head_sha": "new-parent",
            }
        )
    )

    comment = render_stacked_pull_request_review_comment(decision)

    assert decision.stale_rebase_required is True
    assert decision.approval_ready is False
    assert "must rebase" in "\n".join(decision.approval_blockers)
    assert "lower-layer-change comments" in comment


def test_stacked_review_reports_conflicts_to_developer_agent_without_merge() -> None:
    decision = decide_stacked_pull_request_review(
        StackedPullRequestReviewContext(
            **{
                **_stacked_review_context().__dict__,
                "detected_conflicts": ("src/app.py conflicts with lower layer",),
            }
        )
    )

    assert decision.approval_ready is False
    assert decision.merge_ready is False
    assert any("Developer Agent" in blocker for blocker in decision.approval_blockers)
    assert decision.layer_local_comments == (
        "Layer-local conflict handoff: src/app.py conflicts with lower layer",
    )


def test_stacked_review_queue_strategy_can_merge_upper_layer_when_supported() -> None:
    decision = decide_stacked_pull_request_review(
        StackedPullRequestReviewContext(
            **{
                **_stacked_review_context().__dict__,
                "merge_queue_supported": True,
                "branch_protection_supports_stack_merge": True,
                "required_lower_layer_merged": False,
            }
        )
    )

    assert decision.approval_ready is True
    assert decision.merge_ready is True
    assert decision.merge_strategy is StackedReviewMergeStrategy.QUEUED_STACK_MERGE


def test_stacked_review_records_base_and_head_sha_for_each_layer() -> None:
    decision = decide_stacked_pull_request_review(_stacked_review_context())

    payload = stacked_review_layer_record_to_dict(decision.review_record)

    assert payload["reviewed_base_sha"] == "parent-sha"
    assert payload["reviewed_head_sha"] == "head-sha"
    assert payload["stack_layer"] == 2
    assert payload["merge_strategy"] == "bottom-up"


def _review_input() -> PullRequestReviewInput:
    return PullRequestReviewInput(
        review_record_id="review-AGENT-48-PR-48",
        jira_issue_key="AGENT-48",
        story_summary="Implement Review Agent PR Review Workflow",
        acceptance_criteria=("Review Agent reads PR diff.",),
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/48",
        pull_request_number=48,
        head_branch="feature/AGENT-48-review-agent-pr-workflow",
        base_branch="main",
        head_sha="abc1234",
        changed_files=("src/agentic_boilerplate/domain/review_record.py",),
        related_tests=("tests/test_review_record.py",),
        diff_summary="Adds Review Agent workflow records.",
        direct_contracts=("ReviewRecord",),
    )


def _routing() -> ReviewModelRouting:
    return ReviewModelRouting(
        model="gpt-5.5",
        reasoning=ReasoningLevel.MEDIUM,
        speed="normal",
        rationale="Diff-first review with no risk escalation.",
    )


def _stacked_review_context() -> StackedPullRequestReviewContext:
    return StackedPullRequestReviewContext(
        review_record_id="review-AGENT-690-PR-201-layer-2",
        jira_issue_key="AGENT-690",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/201",
        pull_request_number=201,
        stack_id="r12-s7-stack-core",
        lane_id="review-core",
        stack_layer=2,
        stack_trunk="main",
        head_branch="feature/AGENT-690-review-stacked-pr-workflow",
        base_branch="feature/AGENT-689-developer-stacked-pr-workflow",
        expected_base_branch="feature/AGENT-689-developer-stacked-pr-workflow",
        reviewed_base_sha="parent-sha",
        reviewed_head_sha="head-sha",
        context_pack_path="data/context-packs/AGENT-690/context-pack.md",
        required_lower_layer_approved=True,
        required_lower_layer_merged=True,
    )
