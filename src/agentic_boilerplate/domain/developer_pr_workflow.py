"""Developer pull request creation workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from agentic_boilerplate.domain.developer_branch_workflow import (
    DeveloperCommitStage,
    DeveloperCommitStageStatus,
    DeveloperStackExecutionMode,
)
from agentic_boilerplate.domain.story_backed_change_policy import (
    StoryBackedChangeSurface,
    build_story_backed_change_policy_decision,
    render_manual_jira_pr_visibility_fallback,
)
from agentic_boilerplate.integrations.github import GitHubPullRequestFields, GitHubPullRequestMetadata
from agentic_boilerplate.integrations.github import GitHubRepositoryAdapter


DEVELOPER_PR_CREATED_JIRA_STATUS = "DEV COMPLETED"


@dataclass(frozen=True)
class DeveloperPullRequestStackMetadata:
    """Stacked PR details rendered into PR and Jira handoff metadata."""

    stack_id: str = ""
    lane_id: str = ""
    execution_mode: DeveloperStackExecutionMode = DeveloperStackExecutionMode.BASE_BRANCH_FALLBACK
    stack_layer: int = 0
    stack_trunk: str = ""
    parent_story_key: str = ""
    parent_branch: str = ""
    parent_pull_request_number: int = 0
    parent_pull_request_url: str = ""
    child_story_keys: tuple[str, ...] = field(default_factory=tuple)
    child_pull_request_urls: tuple[str, ...] = field(default_factory=tuple)
    context_pack_path: str = ""
    repository: str = ""
    parent_repository: str = ""
    resolver_path_kind: str = "stacked-dependent"
    stale_state: str = ""
    rebase_required: bool = False


@dataclass(frozen=True)
class DeveloperPullRequestPlan:
    """PR creation plan for one completed developer story."""

    jira_issue_key: str
    summary: str
    branch_name: str
    base_branch: str
    stages: tuple[DeveloperCommitStage, ...]
    validation_log_paths: tuple[str, ...]
    related_jira_issue_keys: tuple[str, ...] = ()
    sprint_name: str = ""
    sprint_publication_task_key: str = ""
    change_surface: StoryBackedChangeSurface = StoryBackedChangeSurface.CODE_CHANGE
    affects_boilerplate_behavior: bool = True
    assignment_id: str = ""
    stack_metadata: DeveloperPullRequestStackMetadata = field(default_factory=DeveloperPullRequestStackMetadata)


@dataclass(frozen=True)
class DeveloperPullRequestResult:
    """Durable PR creation result stored for assignment/review workflows."""

    jira_issue_key: str
    assignment_id: str
    pull_request_number: int
    pull_request_url: str
    head_branch: str
    base_branch: str
    head_sha: str
    created: bool


@dataclass(frozen=True)
class DeveloperPullRequestWorkflowIssue:
    """Validation issue for PR creation."""

    field: str
    message: str


class DeveloperPullRequestWorkflowError(ValueError):
    """Raised when PR creation is not allowed."""

    def __init__(self, issues: Sequence[DeveloperPullRequestWorkflowIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_developer_pull_request_workflow_issues(self.issues))


def validate_developer_pull_request_plan(plan: DeveloperPullRequestPlan) -> list[DeveloperPullRequestWorkflowIssue]:
    """Return PR eligibility issues."""

    issues: list[DeveloperPullRequestWorkflowIssue] = []
    _require_text(issues, "jira_issue_key", plan.jira_issue_key)
    _require_text(issues, "summary", plan.summary)
    _require_text(issues, "branch_name", plan.branch_name)
    _require_text(issues, "base_branch", plan.base_branch)
    if plan.sprint_publication_task_key and not plan.sprint_name.strip():
        issues.append(
            DeveloperPullRequestWorkflowIssue(
                "sprint_name",
                "Sprint name is required when a sprint publication task is provided.",
            )
        )
    if not plan.stages:
        issues.append(DeveloperPullRequestWorkflowIssue("stages", "At least one completed development stage is required."))
    if len(plan.validation_log_paths) < len(plan.stages):
        issues.append(
            DeveloperPullRequestWorkflowIssue(
                "validation_log_paths",
                "Every development stage must have durable validation evidence before PR creation.",
            )
        )
    for index, path in enumerate(plan.validation_log_paths):
        _require_text(issues, f"validation_log_paths[{index}]", path)
    for index, stage in enumerate(plan.stages):
        if stage.status != DeveloperCommitStageStatus.COMMITTED:
            issues.append(
                DeveloperPullRequestWorkflowIssue(
                    f"stages[{index}].status",
                    "Development stage must be committed before PR creation.",
                )
            )
        _require_text(issues, f"stages[{index}].jira_subtask_key", stage.jira_subtask_key)
        _require_text(issues, f"stages[{index}].commit_sha", stage.commit_sha)
    _validate_stack_metadata(issues, plan)
    return issues


def require_ready_for_pull_request(plan: DeveloperPullRequestPlan) -> DeveloperPullRequestPlan:
    """Raise when a PR cannot yet be created."""

    issues = validate_developer_pull_request_plan(plan)
    if issues:
        raise DeveloperPullRequestWorkflowError(issues)
    return plan


def render_developer_pull_request_body(plan: DeveloperPullRequestPlan) -> str:
    """Render a PR description with Jira, subtask, commit, and validation links."""

    policy = build_story_backed_change_policy_decision(plan.change_surface)
    lines = [
        f"Jira: {plan.jira_issue_key}",
        "",
        "## Summary",
        f"- {plan.summary}",
        f"- Change surface: {plan.change_surface.value}",
        f"- Affects boilerplate behavior: {'yes' if plan.affects_boilerplate_behavior else 'no'}",
    ]
    if plan.sprint_name.strip():
        lines.append(f"- Sprint: {plan.sprint_name.strip()}")
    if plan.sprint_publication_task_key.strip():
        lines.append(f"- Sprint publication task: {plan.sprint_publication_task_key.strip()}")
    if plan.related_jira_issue_keys:
        lines.append(f"- Related Jira: {', '.join(plan.related_jira_issue_keys)}")
    if _stack_metadata_is_present(plan.stack_metadata):
        lines.extend(["", "## Stacked PR"])
        lines.extend(_stack_metadata_lines(plan))
    lines.extend(
        [
            "",
            "## Development Subtasks",
        ]
    )
    for stage in plan.stages:
        lines.append(f"- {stage.jira_subtask_key}: {stage.title} ({stage.commit_sha})")
    lines.extend(["", "## Validation Evidence"])
    for path in plan.validation_log_paths:
        lines.append(f"- {path}")
    lines.extend(
        [
            "",
            "## Workflow",
            "- All development subtasks are committed.",
            "- Durable validation evidence is attached before PR creation.",
            "- Jira-visible pull request trace is required for the story-backed change.",
            "- Review and merge are handled by the Review Agent workflow.",
        ]
    )
    lines.extend(["", "## Validation Expectations"])
    for step in policy.validation_steps:
        lines.append(f"- {step}")
    return "\n".join(lines).strip()


def github_pull_request_fields_for_plan(
    plan: DeveloperPullRequestPlan,
    *,
    draft: bool = False,
) -> GitHubPullRequestFields:
    """Build GitHub PR fields from a validated developer PR plan."""

    require_ready_for_pull_request(plan)
    return GitHubPullRequestFields(
        title=f"{plan.jira_issue_key} {plan.summary}",
        head=plan.branch_name,
        base=plan.base_branch,
        body=render_developer_pull_request_body(plan),
        draft=draft,
    )


def execute_developer_pull_request_creation(
    adapter: GitHubRepositoryAdapter,
    plan: DeveloperPullRequestPlan,
    *,
    draft: bool = False,
) -> DeveloperPullRequestResult:
    """Create a GitHub PR through the configured adapter and return durable metadata."""

    fields = github_pull_request_fields_for_plan(plan, draft=draft)
    metadata = adapter.create_pull_request(fields)
    return developer_pull_request_result_from_metadata(plan, metadata)


def developer_pull_request_result_from_metadata(
    plan: DeveloperPullRequestPlan,
    metadata: GitHubPullRequestMetadata,
) -> DeveloperPullRequestResult:
    """Convert GitHub adapter metadata into durable workflow result."""

    return DeveloperPullRequestResult(
        jira_issue_key=plan.jira_issue_key,
        assignment_id=plan.assignment_id,
        pull_request_number=metadata.number,
        pull_request_url=metadata.html_url,
        head_branch=metadata.head,
        base_branch=metadata.base,
        head_sha=metadata.head_sha,
        created=True,
    )


def developer_pull_request_result_to_dict(result: DeveloperPullRequestResult) -> dict[str, Any]:
    """Convert a PR result into JSON-compatible data."""

    return {
        "jira_issue_key": result.jira_issue_key,
        "assignment_id": result.assignment_id,
        "pull_request_number": result.pull_request_number,
        "pull_request_url": result.pull_request_url,
        "head_branch": result.head_branch,
        "base_branch": result.base_branch,
        "head_sha": result.head_sha,
        "created": result.created,
    }


def render_jira_pr_created_comment(
    plan: DeveloperPullRequestPlan,
    result: DeveloperPullRequestResult,
) -> str:
    """Render Jira comment text for PR visibility."""

    commit_shas = tuple(stage.commit_sha for stage in plan.stages if stage.commit_sha.strip())
    fallback = render_manual_jira_pr_visibility_fallback(
        jira_issue_key=result.jira_issue_key,
        pull_request_url=result.pull_request_url,
        branch_name=result.head_branch,
        commit_shas=commit_shas,
        validation_paths=plan.validation_log_paths,
        related_jira_issue_keys=plan.related_jira_issue_keys,
        sprint_name=plan.sprint_name,
        sprint_publication_task_key=plan.sprint_publication_task_key,
        change_surface=plan.change_surface,
        affects_boilerplate_behavior=plan.affects_boilerplate_behavior,
    )
    return (
        f"Developer pull request created for {result.jira_issue_key}.\n\n"
        f"{fallback}\n"
        f"{_jira_stack_metadata_comment(plan)}\n"
        f"Base: {result.base_branch}\n"
        f"Head SHA: {result.head_sha}"
    ).strip()


def jira_status_after_developer_pull_request_created() -> str:
    """Return the Jira story status target after developer PR creation."""

    return DEVELOPER_PR_CREATED_JIRA_STATUS


def format_developer_pull_request_workflow_issues(
    issues: Sequence[DeveloperPullRequestWorkflowIssue],
) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _validate_stack_metadata(
    issues: list[DeveloperPullRequestWorkflowIssue],
    plan: DeveloperPullRequestPlan,
) -> None:
    metadata = plan.stack_metadata
    if not _stack_metadata_is_present(metadata):
        return
    _require_text(issues, "stack_metadata.stack_id", metadata.stack_id)
    _require_text(issues, "stack_metadata.lane_id", metadata.lane_id)
    _require_text(issues, "stack_metadata.stack_trunk", metadata.stack_trunk)
    _require_text(issues, "stack_metadata.context_pack_path", metadata.context_pack_path)
    _require_text(issues, "stack_metadata.repository", metadata.repository)
    if metadata.stack_layer < 1:
        issues.append(DeveloperPullRequestWorkflowIssue("stack_metadata.stack_layer", "Stack layer must be 1 or greater."))
    if metadata.resolver_path_kind != "stacked-dependent":
        issues.append(
            DeveloperPullRequestWorkflowIssue(
                "stack_metadata.resolver_path_kind",
                "Developer stacked PR creation is allowed only for stacked-dependent paths.",
            )
        )
    if metadata.parent_repository.strip() and _normalized(metadata.parent_repository) != _normalized(metadata.repository):
        issues.append(
            DeveloperPullRequestWorkflowIssue(
                "stack_metadata.repository",
                "Stacked PR branches must stay in the same repository; cross-fork or cross-repo stacks are blocked.",
            )
        )
    if metadata.rebase_required:
        issues.append(
            DeveloperPullRequestWorkflowIssue(
                "stack_metadata.rebase_required",
                "Stacked branch is stale and must be rebased before PR creation.",
            )
        )
    if metadata.stack_layer <= 1:
        if metadata.stack_trunk.strip() and plan.base_branch.strip() != metadata.stack_trunk.strip():
            issues.append(
                DeveloperPullRequestWorkflowIssue(
                    "base_branch",
                    "First stack layer must target the configured stack trunk.",
                )
            )
    else:
        _require_text(issues, "stack_metadata.parent_story_key", metadata.parent_story_key)
        _require_text(issues, "stack_metadata.parent_branch", metadata.parent_branch)
        if metadata.parent_branch.strip() and plan.base_branch.strip() != metadata.parent_branch.strip():
            issues.append(
                DeveloperPullRequestWorkflowIssue(
                    "base_branch",
                    "Upper stack layer PR must target the previous stack layer branch.",
                )
            )


def _stack_metadata_is_present(metadata: DeveloperPullRequestStackMetadata) -> bool:
    return any(
        (
            metadata.stack_id.strip(),
            metadata.lane_id.strip(),
            metadata.stack_layer,
            metadata.stack_trunk.strip(),
            metadata.parent_story_key.strip(),
            metadata.parent_branch.strip(),
            metadata.parent_pull_request_number,
            metadata.parent_pull_request_url.strip(),
            metadata.child_story_keys,
            metadata.child_pull_request_urls,
            metadata.context_pack_path.strip(),
            metadata.repository.strip(),
            metadata.parent_repository.strip(),
            metadata.stale_state.strip(),
            metadata.rebase_required,
        )
    )


def _stack_metadata_lines(plan: DeveloperPullRequestPlan) -> list[str]:
    metadata = plan.stack_metadata
    return [
        f"- Stack ID: {metadata.stack_id}",
        f"- Lane ID: {metadata.lane_id}",
        f"- Mode: {metadata.execution_mode.value}",
        f"- Layer: {metadata.stack_layer}",
        f"- Trunk: {metadata.stack_trunk}",
        f"- Base branch: {plan.base_branch}",
        f"- Parent story: {metadata.parent_story_key or 'none'}",
        f"- Parent branch: {metadata.parent_branch or 'none'}",
        f"- Parent PR: {_parent_pr_display(metadata)}",
        f"- Child stories: {', '.join(metadata.child_story_keys) if metadata.child_story_keys else 'none known'}",
        f"- Child PRs: {', '.join(metadata.child_pull_request_urls) if metadata.child_pull_request_urls else 'none known'}",
        f"- Context pack: {metadata.context_pack_path}",
        f"- Stale state: {metadata.stale_state or 'fresh'}",
    ]


def _jira_stack_metadata_comment(plan: DeveloperPullRequestPlan) -> str:
    if not _stack_metadata_is_present(plan.stack_metadata):
        return ""
    metadata = plan.stack_metadata
    return (
        "Stacked PR metadata:\n"
        f"Stack: {metadata.stack_id}, lane: {metadata.lane_id}, layer: {metadata.stack_layer}, "
        f"mode: {metadata.execution_mode.value}.\n"
        f"Parent PR: {_parent_pr_display(metadata)}. Context pack: {metadata.context_pack_path}."
    )


def _parent_pr_display(metadata: DeveloperPullRequestStackMetadata) -> str:
    if metadata.parent_pull_request_number and metadata.parent_pull_request_url:
        return f"#{metadata.parent_pull_request_number} {metadata.parent_pull_request_url}"
    if metadata.parent_pull_request_number:
        return f"#{metadata.parent_pull_request_number}"
    return metadata.parent_pull_request_url or "none known"


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _require_text(issues: list[DeveloperPullRequestWorkflowIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(DeveloperPullRequestWorkflowIssue(field=field, message="Value is required."))
