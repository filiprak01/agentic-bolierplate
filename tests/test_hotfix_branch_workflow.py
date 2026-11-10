from agentic_boilerplate.domain import (
    HotfixBranchWorkflowError,
    HotfixBugReference,
    HotfixSourceType,
    ReleaseVersion,
    build_hotfix_branch_name,
    build_hotfix_branch_plan,
    classify_hotfix_source_ref,
    hotfix_branch_plan_from_dict,
    hotfix_branch_plan_to_dict,
    normalize_hotfix_slug,
    render_hotfix_branch_plan,
    validate_hotfix_branch_name,
)


def test_hotfix_branch_plan_uses_hotfix_naming_and_release_branch_source() -> None:
    plan = _plan(source_ref="release/1.9.x")

    assert plan.hotfix_version.value == "1.9.1"
    assert plan.hotfix_branch_name == "hotfix/1.9.1-AGENT-900"
    assert plan.source_type is HotfixSourceType.RELEASE_BRANCH
    assert plan.merge_back_target == "release/1.9.x"
    assert plan.forward_port_target == "main"
    assert plan.conflict_resolution_required is False
    assert plan.manual_approval_points == (
        "Release Manager approves hotfix scope.",
        "Product Owner accepts the fixed behavior before release.",
    )


def test_hotfix_branch_plan_accepts_prior_release_tag_source() -> None:
    plan = _plan(source_ref="v1.9.0")

    assert plan.source_type is HotfixSourceType.RELEASE_TAG
    assert classify_hotfix_source_ref("v1.9.0", plan.hotfix_version) is HotfixSourceType.RELEASE_TAG


def test_hotfix_branch_name_parser_and_slug_normalization() -> None:
    version, slug = validate_hotfix_branch_name("hotfix/1.9.2-AGENT-900-prod-fix")

    assert version.value == "1.9.2"
    assert slug == "AGENT-900-prod-fix"
    assert normalize_hotfix_slug("AGENT-900 prod fix") == "AGENT-900-prod-fix"
    assert build_hotfix_branch_name(ReleaseVersion(1, 9, 2), "AGENT-900 prod fix") == (
        "hotfix/1.9.2-AGENT-900-prod-fix"
    )


def test_hotfix_branch_plan_round_trips_and_renders_evidence() -> None:
    plan = _plan(source_ref="release/1.9.x", conflict_resolution_required=True)

    restored = hotfix_branch_plan_from_dict(hotfix_branch_plan_to_dict(plan))
    rendered = render_hotfix_branch_plan(restored)

    assert restored == plan
    assert "# Hotfix Branch Plan - 1.9.1" in rendered
    assert "- Hotfix branch: hotfix/1.9.1-AGENT-900" in rendered
    assert "- Fixed bug: AGENT-900 - Production login failure" in rendered
    assert "- Conflict resolution required: yes" in rendered
    assert "Release Manager approves hotfix scope." in rendered


def test_hotfix_source_ref_must_match_release_line() -> None:
    try:
        _plan(source_ref="release/1.8.x")
    except HotfixBranchWorkflowError as error:
        assert "same major and minor release line" in str(error)
    else:
        raise AssertionError("Expected mismatched release line to fail")


def test_hotfix_source_tag_must_be_earlier_than_hotfix_version() -> None:
    try:
        _plan(source_ref="v1.9.1")
    except HotfixBranchWorkflowError as error:
        assert "source release tag must be earlier" in str(error)
    else:
        raise AssertionError("Expected non-prior source tag to fail")


def test_hotfix_branch_plan_requires_bug_and_manual_approval_points() -> None:
    try:
        build_hotfix_branch_plan(
            major_update=1,
            sprint_scope=9,
            hotfix=1,
            jira_key_or_slug="AGENT-900",
            source_ref="release/1.9.x",
            fixed_bug=HotfixBugReference(issue_key="", summary="Production login failure"),
            manual_approval_points=("Release Manager approves hotfix scope.",),
            rationale="Invalid missing bug key.",
        )
    except HotfixBranchWorkflowError as error:
        assert "fixed_bug.issue_key is required" in str(error)
    else:
        raise AssertionError("Expected missing bug key to fail")

    try:
        build_hotfix_branch_plan(
            major_update=1,
            sprint_scope=9,
            hotfix=1,
            jira_key_or_slug="AGENT-900",
            source_ref="release/1.9.x",
            fixed_bug=_bug(),
            manual_approval_points=(),
            rationale="Invalid missing approval points.",
        )
    except HotfixBranchWorkflowError as error:
        assert "manual_approval_points must contain at least one point" in str(error)
    else:
        raise AssertionError("Expected missing approval points to fail")


def test_hotfix_branch_requires_positive_hotfix_number() -> None:
    try:
        build_hotfix_branch_name(ReleaseVersion(1, 9, 0), "AGENT-900")
    except HotfixBranchWorkflowError as error:
        assert "version.hotfix must be greater than zero" in str(error)
    else:
        raise AssertionError("Expected zero hotfix branch to fail")


def _plan(*, source_ref: str, conflict_resolution_required: bool = False):
    return build_hotfix_branch_plan(
        major_update=1,
        sprint_scope=9,
        hotfix=1,
        jira_key_or_slug="AGENT-900",
        source_ref=source_ref,
        fixed_bug=_bug(),
        conflict_resolution_required=conflict_resolution_required,
        rationale="Fix production login failure on the release maintenance line.",
    )


def _bug() -> HotfixBugReference:
    return HotfixBugReference(
        issue_key="AGENT-900",
        summary="Production login failure",
        environment="prod",
        severity="critical",
    )
