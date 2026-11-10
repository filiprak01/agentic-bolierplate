from agentic_boilerplate.domain import (
    StoryBackedChangeSurface,
    build_process_change_branch_name,
    build_story_backed_change_policy_decision,
    plan_github_validation_fallback,
    render_manual_jira_pr_visibility_fallback,
)


def test_docs_and_code_changes_have_different_policy_requirements() -> None:
    docs = build_story_backed_change_policy_decision(StoryBackedChangeSurface.DOCUMENTATION_ONLY)
    code = build_story_backed_change_policy_decision(StoryBackedChangeSurface.CODE_CHANGE)

    assert docs.jira_story_required is False
    assert docs.affects_boilerplate_behavior is False
    assert "markdown" in docs.validation_steps[1].lower()
    assert code.jira_story_required is True
    assert code.affects_boilerplate_behavior is True


def test_process_change_branch_name_uses_story_or_sprint_reference() -> None:
    assert (
        build_process_change_branch_name(jira_issue_key="AGENT-138", slug="retro closure")
        == "process/AGENT-138-retro-closure"
    )
    assert (
        build_process_change_branch_name(sprint_name="Sprint 8", slug="process closure")
        == "docs/sprint-8-process-closure"
    )


def test_manual_jira_visibility_fallback_includes_required_traceability() -> None:
    comment = render_manual_jira_pr_visibility_fallback(
        jira_issue_key="AGENT-138",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/138",
        branch_name="process/AGENT-138-retro-closure",
        commit_shas=("abc1234", "def5678"),
        validation_paths=("docs/sprint-8-retro.md",),
        related_jira_issue_keys=("AGENT-40",),
        sprint_name="Sprint 8",
        sprint_publication_task_key="AGENT-283",
        change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
        affects_boilerplate_behavior=False,
        review_result="approved",
        merge_commit_sha="fedcba9",
    )

    assert "PR visibility fallback for AGENT-138." in comment
    assert "Branch: process/AGENT-138-retro-closure" in comment
    assert "Commits:" in comment
    assert "Validation evidence:" in comment
    assert "Review result: approved" in comment
    assert "Merge commit: fedcba9" in comment


def test_github_validation_fallback_not_required_when_github_and_jira_are_visible() -> None:
    decision = plan_github_validation_fallback(
        jira_issue_key="AGENT-138",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/138",
        branch_name="process/AGENT-138-retro-closure",
        commit_shas=("abc1234",),
        validation_paths=("docs/sprint-8-retro.md",),
        github_validation_available=True,
        jira_pr_link_visible=True,
    )

    assert decision.fallback_required is False
    assert decision.validation_visible is True
    assert decision.reasons == ()
    assert decision.jira_comment == ""


def test_github_validation_fallback_comment_is_required_when_github_validation_is_unavailable() -> None:
    decision = plan_github_validation_fallback(
        jira_issue_key="AGENT-138",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/138",
        branch_name="process/AGENT-138-retro-closure",
        commit_shas=("abc1234",),
        validation_paths=("docs/sprint-8-retro.md",),
        github_validation_available=False,
        jira_pr_link_visible=True,
        related_jira_issue_keys=("AGENT-40",),
        sprint_name="Sprint 8",
        sprint_publication_task_key="AGENT-283",
        change_surface=StoryBackedChangeSurface.PROCESS_DOCUMENTATION,
        affects_boilerplate_behavior=False,
    )

    assert decision.fallback_required is True
    assert decision.validation_visible is False
    assert decision.reasons == ("github-validation-unavailable",)
    assert "PR visibility fallback for AGENT-138." in decision.jira_comment
    assert "Related Jira: AGENT-40" in decision.jira_comment
    assert "Sprint publication task: AGENT-283" in decision.jira_comment


def test_github_validation_fallback_comment_is_required_when_jira_pr_link_is_missing() -> None:
    decision = plan_github_validation_fallback(
        jira_issue_key="AGENT-138",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/138",
        branch_name="process/AGENT-138-retro-closure",
        commit_shas=("abc1234",),
        validation_paths=("docs/sprint-8-retro.md",),
        github_validation_available=True,
        jira_pr_link_visible=False,
    )

    assert decision.fallback_required is True
    assert decision.validation_visible is False
    assert decision.reasons == ("jira-pr-link-not-visible",)
    assert "PR: https://github.com/example-org/agentic-boilerplate/pull/138" in decision.jira_comment


def test_existing_manual_github_validation_fallback_satisfies_visibility() -> None:
    decision = plan_github_validation_fallback(
        jira_issue_key="AGENT-138",
        pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/138",
        branch_name="process/AGENT-138-retro-closure",
        commit_shas=("abc1234",),
        validation_paths=("docs/sprint-8-retro.md",),
        github_validation_available=False,
        jira_pr_link_visible=False,
        manual_fallback_present=True,
    )

    assert decision.fallback_required is False
    assert decision.validation_visible is True
    assert decision.reasons == (
        "github-validation-unavailable",
        "jira-pr-link-not-visible",
        "manual-fallback-already-present",
    )
    assert decision.jira_comment == ""


def test_github_validation_fallback_requires_traceability_inputs() -> None:
    try:
        plan_github_validation_fallback(
            jira_issue_key="AGENT-138",
            pull_request_url=" ",
            branch_name="process/AGENT-138-retro-closure",
            commit_shas=("abc1234",),
            validation_paths=("docs/sprint-8-retro.md",),
            github_validation_available=False,
            jira_pr_link_visible=False,
        )
    except ValueError as exc:
        assert "pull_request_url" in str(exc)
    else:
        raise AssertionError("Expected blank pull_request_url to fail fallback planning.")
