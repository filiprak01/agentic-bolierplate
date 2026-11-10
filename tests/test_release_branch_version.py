from agentic_boilerplate.domain import (
    DEFAULT_MAIN_BRANCH,
    ReleaseAutomationAction,
    ReleaseBranchPlan,
    ReleaseBranchWorkflowError,
    ReleaseIncludedWorkItem,
    build_release_branch_automation_plan,
    build_release_branch_plan,
    release_branch_plan_from_dict,
    release_branch_plan_to_dict,
    render_release_branch_automation_checklist,
    render_release_branch_plan,
    validate_release_branch_name,
    validate_version_tag_name,
)


def test_release_branch_plan_uses_release_branch_and_version_tag_conventions() -> None:
    plan = _plan()

    assert plan.release_version.value == "1.9.0"
    assert plan.release_branch_name == "release/1.9.x"
    assert plan.version_tag_name == "v1.9.0"
    assert plan.source_ref == "main"
    assert plan.main_branch == DEFAULT_MAIN_BRANCH
    assert plan.merge_back_target == "release/1.9.x"
    assert plan.merge_forward_required is True
    assert plan.manual_approval_required is True


def test_release_branch_plan_records_included_work_items() -> None:
    plan = _plan()

    assert [item.issue_key for item in plan.included_work_items] == ["AGENT-52", "AGENT-53"]
    assert plan.included_work_items[0].pull_request_url.endswith("/pull/49")
    assert plan.included_work_items[0].merge_commit_sha == "a7cff25"


def test_release_branch_and_tag_validators_parse_version_metadata() -> None:
    branch_version = validate_release_branch_name("release/2.11.x")
    tag_version = validate_version_tag_name("v2.11.3")

    assert branch_version.value == "2.11.0"
    assert tag_version.value == "2.11.3"


def test_release_1_1_policy_examples_are_valid_and_patchable() -> None:
    branch_version = validate_release_branch_name("release/1.1.x")
    stable_tag = validate_version_tag_name("v1.1.0")
    patch_tag = validate_version_tag_name("v1.1.1")

    assert branch_version.value == "1.1.0"
    assert stable_tag.value == "1.1.0"
    assert patch_tag.value == "1.1.1"


def test_release_1_1_branch_plan_records_dogfooding_fix_scope() -> None:
    plan = build_release_branch_plan(
        major_update=1,
        sprint_scope=1,
        hotfix=0,
        source_ref="main",
        included_work_items=(
            ReleaseIncludedWorkItem(
                issue_key="AGENT-427",
                summary="Fix Docker API keepalive stability",
            ),
        ),
        rationale="Release 1.1 includes approved MVP dogfooding fixes that unblock operator reliability.",
    )

    rendered = render_release_branch_plan(plan)

    assert plan.release_branch_name == "release/1.1.x"
    assert plan.version_tag_name == "v1.1.0"
    assert "AGENT-427" in rendered
    assert "dogfooding fixes" in rendered


def test_release_branch_plan_round_trips_and_renders_evidence() -> None:
    plan = _plan()

    restored = release_branch_plan_from_dict(release_branch_plan_to_dict(plan))
    rendered = render_release_branch_plan(restored)

    assert restored == plan
    assert "# Release Branch Plan - 1.9.0" in rendered
    assert "- Release branch: release/1.9.x" in rendered
    assert "- Version tag: v1.9.0" in rendered
    assert "AGENT-53" in rendered
    assert "Merge forward required: yes" in rendered


def test_release_branch_automation_is_ready_after_regression_passes() -> None:
    automation = build_release_branch_automation_plan(
        branch_plan=_plan(),
        regression_passed=True,
        regression_evidence_path="data/agent-logs/REGRESSION-R12-S6/regression.md",
    )

    assert automation.ready_to_execute is True
    assert automation.blockers == ()
    assert automation.actions[0] is ReleaseAutomationAction.FETCH_MAIN
    assert "git switch -c release/1.9.x main" in automation.git_commands
    assert "git tag -a v1.9.0" in "\n".join(automation.git_commands)
    assert "Ready to execute: yes" in automation.checklist_markdown


def test_release_branch_automation_blocks_failed_regression_or_open_bugs() -> None:
    automation = build_release_branch_automation_plan(
        branch_plan=_plan(),
        regression_passed=False,
        regression_evidence_path=" ",
        blocking_bug_keys=("AGENT-999",),
    )

    assert automation.ready_to_execute is False
    assert automation.actions == ()
    assert automation.git_commands == ()
    assert "regression must pass" in automation.blockers[0]
    assert "regression evidence path is required" in automation.blockers
    assert "blocking bugs must be resolved" in automation.blockers[2]
    assert "No commands are executable" in automation.checklist_markdown


def test_release_branch_automation_checklist_renders_manual_approval_and_work() -> None:
    checklist = render_release_branch_automation_checklist(
        branch_plan=_plan(),
        regression_passed=True,
        regression_evidence_path="data/agent-logs/REGRESSION-R12-S6/regression.md",
    )

    assert "# Release Branch Automation Checklist - 1.9.0" in checklist
    assert "- Manual approval required: yes" in checklist
    assert "- [ ] Release scope matches included work items." in checklist
    assert "git push origin release/1.9.x" in checklist


def test_release_branch_plan_rejects_missing_included_work() -> None:
    try:
        build_release_branch_plan(
            major_update=1,
            sprint_scope=9,
            hotfix=0,
            source_ref="main",
            included_work_items=(),
            rationale="Invalid release without included work.",
        )
    except ReleaseBranchWorkflowError as error:
        assert "included_work_items must contain at least one item" in str(error)
    else:
        raise AssertionError("Expected empty included work to fail")


def test_release_branch_plan_rejects_invalid_branch_or_tag_names() -> None:
    try:
        validate_release_branch_name("release/1.9.0")
    except ReleaseBranchWorkflowError as error:
        assert "release/{MAJOR}.{MINOR}.x" in str(error)
    else:
        raise AssertionError("Expected invalid release branch to fail")

    try:
        validate_version_tag_name("1.9.0")
    except ReleaseBranchWorkflowError as error:
        assert "v{MAJOR}.{MINOR}.{PATCH}" in str(error)
    else:
        raise AssertionError("Expected invalid version tag to fail")


def test_release_branch_plan_from_dict_rejects_inconsistent_metadata() -> None:
    data = release_branch_plan_to_dict(_plan())
    data["release_branch_name"] = "release/1.10.x"

    try:
        release_branch_plan_from_dict(data)
    except ReleaseBranchWorkflowError as error:
        assert "release_branch_name must be release/1.9.x" in str(error)
    else:
        raise AssertionError("Expected inconsistent release branch metadata to fail")


def _plan() -> ReleaseBranchPlan:
    return build_release_branch_plan(
        major_update=1,
        sprint_scope=9,
        hotfix=0,
        source_ref="main",
        included_work_items=(
            ReleaseIncludedWorkItem(
                issue_key="AGENT-52",
                summary="Release Manager scope selection",
                pull_request_url="https://github.com/example-org/agentic-boilerplate/pull/49",
                merge_commit_sha="a7cff25",
            ),
            ReleaseIncludedWorkItem(
                issue_key="AGENT-53",
                summary="Release branch and version tag workflow",
            ),
        ),
        rationale="Prepare a release maintenance branch for MVP Sprint 9.",
    )
