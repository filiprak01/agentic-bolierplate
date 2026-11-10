"""Developer branch, commit, and validation workflow contracts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeveloperCommitStageStatus(str, Enum):
    """Developer commit stage lifecycle states."""

    PLANNED = "planned"
    VALIDATION_FAILED = "validation_failed"
    VALIDATED = "validated"
    COMMITTED = "committed"


class DeveloperStackExecutionMode(str, Enum):
    """How a developer creates stacked PR branches and pull requests."""

    GH_STACK = "gh-stack"
    BASE_BRANCH_FALLBACK = "base-branch-fallback"


TERMINAL_DEVELOPER_COMMIT_STAGE_STATUSES: frozenset[DeveloperCommitStageStatus] = frozenset(
    {DeveloperCommitStageStatus.COMMITTED}
)


STACKED_DEVELOPER_CONTINUE_PARENT_STATES: frozenset[str] = frozenset(
    {
        "review-pending",
        "in-review",
        "dev-completed",
        "dev completed",
        "test-completed",
        "test completed",
        "accepted/done",
        "accepted / done",
        "merged",
    }
)


@dataclass(frozen=True)
class DeveloperCommitStage:
    """One development subtask stage that should end with one commit."""

    stage_id: str
    jira_subtask_key: str
    title: str
    validation_commands: tuple[str, ...]
    expected_changed_paths: tuple[str, ...] = ()
    commit_message: str = ""
    commit_sha: str = ""
    status: DeveloperCommitStageStatus = DeveloperCommitStageStatus.PLANNED


@dataclass(frozen=True)
class DeveloperStackBranchContext:
    """Resolved stack inputs the Developer Agent must check before branching."""

    stack_id: str
    lane_id: str
    stack_trunk: str
    stack_layer: int
    repository: str
    parent_repository: str = ""
    parent_story_key: str = ""
    parent_branch: str = ""
    child_story_keys: tuple[str, ...] = field(default_factory=tuple)
    resolver_path_kind: str = "stacked-dependent"
    execution_mode: DeveloperStackExecutionMode = DeveloperStackExecutionMode.BASE_BRANCH_FALLBACK
    github_auth_ready: bool = True
    parent_story_state: str = ""
    recorded_parent_head_sha: str = ""
    current_parent_head_sha: str = ""


@dataclass(frozen=True)
class DeveloperStackBranchDecision:
    """Branch decision for one Developer Agent stacked story."""

    stack_id: str = ""
    lane_id: str = ""
    execution_mode: DeveloperStackExecutionMode | None = None
    base_branch: str = ""
    can_continue_upper_layer: bool = False
    stale_state: str = ""
    rebase_required: bool = False
    blockers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeveloperValidationCommandResult:
    """Captured output for one developer validation command."""

    command: str
    exit_code: int
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class DeveloperStageValidationResult:
    """Durable validation result for one development stage."""

    jira_issue_key: str
    stage_id: str
    jira_subtask_key: str
    validated_at: str
    command_results: tuple[DeveloperValidationCommandResult, ...]
    commit_sha: str = ""
    output_path: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.command_results) and all(result.passed for result in self.command_results)


@dataclass(frozen=True)
class DeveloperBranchPlan:
    """Branch and commit plan for one Jira story or bug."""

    jira_issue_key: str
    summary: str
    branch_name: str
    base_branch: str
    target_repo_path: str
    stages: tuple[DeveloperCommitStage, ...]
    validation_output_root: str
    stack_decision: DeveloperStackBranchDecision = field(default_factory=DeveloperStackBranchDecision)


@dataclass(frozen=True)
class DeveloperBranchWorkflowIssue:
    """Validation issue for a developer branch plan."""

    field: str
    message: str


class DeveloperBranchWorkflowError(ValueError):
    """Raised when a branch/commit workflow artifact is invalid."""

    def __init__(self, issues: Sequence[DeveloperBranchWorkflowIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_developer_branch_workflow_issues(self.issues))


def build_feature_branch_name(jira_issue_key: str, summary: str, *, max_slug_length: int = 48) -> str:
    """Build `feature/{JIRA_KEY}-{short-slug}` from approved Jira story data."""

    key = jira_issue_key.strip().upper()
    slug = _slugify(summary)[:max_slug_length].strip("-")
    return f"feature/{key}-{slug}" if slug else f"feature/{key}"


def build_developer_branch_plan(
    *,
    jira_issue_key: str,
    summary: str,
    base_branch: str,
    target_repo_path: str,
    stages: Sequence[DeveloperCommitStage],
    branch_name: str = "",
    validation_output_root: str = "",
) -> DeveloperBranchPlan:
    """Create and validate a developer branch and commit workflow plan."""

    clean_key = jira_issue_key.strip().upper()
    plan = DeveloperBranchPlan(
        jira_issue_key=clean_key,
        summary=summary.strip(),
        branch_name=branch_name.strip() or build_feature_branch_name(clean_key, summary),
        base_branch=base_branch.strip(),
        target_repo_path=target_repo_path.strip(),
        stages=tuple(stages),
        validation_output_root=validation_output_root.strip() or f"data/agent-logs/{clean_key}/validation",
    )
    return require_valid_developer_branch_plan(plan)


def build_stacked_developer_branch_plan(
    *,
    jira_issue_key: str,
    summary: str,
    stack_context: DeveloperStackBranchContext,
    target_repo_path: str,
    stages: Sequence[DeveloperCommitStage],
    branch_name: str = "",
    validation_output_root: str = "",
) -> DeveloperBranchPlan:
    """Build a developer branch plan whose base branch comes from stack metadata."""

    decision = resolve_stacked_developer_branch_decision(stack_context)
    if decision.blockers:
        raise DeveloperBranchWorkflowError(
            [
                DeveloperBranchWorkflowIssue("stack_context", blocker)
                for blocker in decision.blockers
            ]
        )
    clean_key = jira_issue_key.strip().upper()
    plan = DeveloperBranchPlan(
        jira_issue_key=clean_key,
        summary=summary.strip(),
        branch_name=branch_name.strip() or build_feature_branch_name(clean_key, summary),
        base_branch=decision.base_branch,
        target_repo_path=target_repo_path.strip(),
        stages=tuple(stages),
        validation_output_root=validation_output_root.strip() or f"data/agent-logs/{clean_key}/validation",
        stack_decision=decision,
    )
    return require_valid_developer_branch_plan(plan)


def resolve_stacked_developer_branch_decision(
    context: DeveloperStackBranchContext,
) -> DeveloperStackBranchDecision:
    """Validate stacked PR branch constraints and choose the branch base."""

    blockers: list[str] = []
    if not context.github_auth_ready:
        blockers.append("GitHub authentication is not ready for stacked branch or PR work.")
    _require_stack_text(blockers, "stack_id", context.stack_id)
    _require_stack_text(blockers, "lane_id", context.lane_id)
    _require_stack_text(blockers, "stack_trunk", context.stack_trunk)
    _require_stack_text(blockers, "repository", context.repository)
    if context.stack_layer < 1:
        blockers.append("Stack layer must be 1 or greater.")
    if context.resolver_path_kind != "stacked-dependent":
        blockers.append("Resolver path is not stacked-dependent; use sequential workflow.")
    if context.parent_repository.strip() and _normalized(context.parent_repository) != _normalized(context.repository):
        blockers.append("Stacked PR branches must stay in the same repository; cross-fork or cross-repo stacks are blocked.")

    base_branch = context.stack_trunk.strip()
    can_continue_upper_layer = context.stack_layer == 1
    if context.stack_layer > 1:
        _require_stack_text(blockers, "parent_story_key", context.parent_story_key)
        _require_stack_text(blockers, "parent_branch", context.parent_branch)
        _require_stack_text(blockers, "parent_story_state", context.parent_story_state)
        base_branch = context.parent_branch.strip()
        can_continue_upper_layer = _normalized(context.parent_story_state) in STACKED_DEVELOPER_CONTINUE_PARENT_STATES
        if context.parent_story_state.strip() and not can_continue_upper_layer:
            blockers.append("Parent story state does not allow upper-layer stacked development.")

    stale_state = ""
    rebase_required = False
    if (
        context.recorded_parent_head_sha.strip()
        and context.current_parent_head_sha.strip()
        and context.recorded_parent_head_sha.strip() != context.current_parent_head_sha.strip()
    ):
        stale_state = "parent-branch-changed"
        rebase_required = True

    return DeveloperStackBranchDecision(
        stack_id=context.stack_id.strip(),
        lane_id=context.lane_id.strip(),
        execution_mode=context.execution_mode,
        base_branch=base_branch,
        can_continue_upper_layer=can_continue_upper_layer,
        stale_state=stale_state,
        rebase_required=rebase_required,
        blockers=tuple(blockers),
    )


def validate_developer_branch_plan(plan: DeveloperBranchPlan) -> list[DeveloperBranchWorkflowIssue]:
    """Return branch workflow validation issues."""

    issues: list[DeveloperBranchWorkflowIssue] = []
    _require_text(issues, "jira_issue_key", plan.jira_issue_key)
    _require_text(issues, "summary", plan.summary)
    _require_text(issues, "branch_name", plan.branch_name)
    _require_text(issues, "base_branch", plan.base_branch)
    _require_text(issues, "target_repo_path", plan.target_repo_path)
    _require_text(issues, "validation_output_root", plan.validation_output_root)
    if plan.stack_decision.blockers:
        issues.extend(
            DeveloperBranchWorkflowIssue("stack_decision", blocker)
            for blocker in plan.stack_decision.blockers
        )

    expected_prefix = f"feature/{plan.jira_issue_key}-"
    if plan.jira_issue_key and not plan.branch_name.startswith(expected_prefix):
        issues.append(
            DeveloperBranchWorkflowIssue(
                field="branch_name",
                message=f"Feature branch must start with {expected_prefix!r}.",
            )
        )

    if not plan.stages:
        issues.append(DeveloperBranchWorkflowIssue(field="stages", message="At least one commit stage is required."))

    stage_ids = [stage.stage_id for stage in plan.stages]
    if len(set(stage_ids)) != len(stage_ids):
        issues.append(DeveloperBranchWorkflowIssue(field="stages", message="Stage IDs must be unique."))

    for index, stage in enumerate(plan.stages):
        _require_text(issues, f"stages[{index}].stage_id", stage.stage_id)
        _require_text(issues, f"stages[{index}].jira_subtask_key", stage.jira_subtask_key)
        _require_text(issues, f"stages[{index}].title", stage.title)
        if not stage.validation_commands:
            issues.append(
                DeveloperBranchWorkflowIssue(
                    field=f"stages[{index}].validation_commands",
                    message="Validation commands are required before a subtask can be completed.",
                )
            )

    return issues


def require_valid_developer_branch_plan(plan: DeveloperBranchPlan) -> DeveloperBranchPlan:
    """Raise when a developer branch plan violates workflow rules."""

    issues = validate_developer_branch_plan(plan)
    if issues:
        raise DeveloperBranchWorkflowError(issues)
    return plan


def next_developer_commit_stage(plan: DeveloperBranchPlan) -> DeveloperCommitStage | None:
    """Return the next non-committed stage."""

    for stage in plan.stages:
        if stage.status not in TERMINAL_DEVELOPER_COMMIT_STAGE_STATUSES:
            return stage
    return None


def commit_message_for_stage(plan: DeveloperBranchPlan, stage: DeveloperCommitStage) -> str:
    """Return the commit message to use for a completed development stage."""

    if stage.commit_message.strip():
        return stage.commit_message.strip()
    return f"{plan.jira_issue_key} {stage.title}".strip()


def mark_stage_validated(
    stage: DeveloperCommitStage,
    validation: DeveloperStageValidationResult,
) -> DeveloperCommitStage:
    """Return a stage marked validated or validation-failed from durable command output."""

    status = DeveloperCommitStageStatus.VALIDATED if validation.passed else DeveloperCommitStageStatus.VALIDATION_FAILED
    return DeveloperCommitStage(
        stage_id=stage.stage_id,
        jira_subtask_key=stage.jira_subtask_key,
        title=stage.title,
        validation_commands=stage.validation_commands,
        expected_changed_paths=stage.expected_changed_paths,
        commit_message=stage.commit_message,
        commit_sha=stage.commit_sha,
        status=status,
    )


def mark_stage_committed(
    stage: DeveloperCommitStage,
    *,
    commit_sha: str,
) -> DeveloperCommitStage:
    """Mark a validated stage committed after its commit is created."""

    if stage.status != DeveloperCommitStageStatus.VALIDATED:
        raise DeveloperBranchWorkflowError(
            [
                DeveloperBranchWorkflowIssue(
                    field="stage.status",
                    message="Stage must be validated before it can be marked committed.",
                )
            ]
        )
    return DeveloperCommitStage(
        stage_id=stage.stage_id,
        jira_subtask_key=stage.jira_subtask_key,
        title=stage.title,
        validation_commands=stage.validation_commands,
        expected_changed_paths=stage.expected_changed_paths,
        commit_message=stage.commit_message,
        commit_sha=commit_sha.strip(),
        status=DeveloperCommitStageStatus.COMMITTED,
    )


def validation_output_path(plan: DeveloperBranchPlan, stage: DeveloperCommitStage, validated_at: str) -> str:
    """Build a deterministic durable path for one stage validation result."""

    stamp = re.sub(r"[^0-9A-Za-z]+", "", validated_at)
    return f"{plan.validation_output_root.rstrip('/')}/{stage.stage_id}-{stamp}.md"


def render_stage_validation_result(validation: DeveloperStageValidationResult) -> str:
    """Render validation evidence as Markdown for Jira comments and local files."""

    lines = [
        f"# Developer Validation - {validation.jira_issue_key} {validation.stage_id}",
        "",
        f"Subtask: {validation.jira_subtask_key}",
        f"Validated at: {validation.validated_at}",
        f"Result: {'PASSED' if validation.passed else 'FAILED'}",
    ]
    if validation.commit_sha:
        lines.append(f"Commit: {validation.commit_sha}")
    lines.extend(["", "## Commands"])
    for result in validation.command_results:
        lines.extend(
            [
                "",
                f"### `{result.command}`",
                "",
                f"Exit code: {result.exit_code}",
                "",
                "```text",
                result.output.strip(),
                "```",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def validation_result_to_dict(validation: DeveloperStageValidationResult) -> dict[str, Any]:
    """Convert a validation result into JSON-compatible data."""

    return {
        "jira_issue_key": validation.jira_issue_key,
        "stage_id": validation.stage_id,
        "jira_subtask_key": validation.jira_subtask_key,
        "validated_at": validation.validated_at,
        "commit_sha": validation.commit_sha,
        "output_path": validation.output_path,
        "passed": validation.passed,
        "command_results": [
            {"command": result.command, "exit_code": result.exit_code, "output": result.output}
            for result in validation.command_results
        ],
    }


def format_developer_branch_workflow_issues(issues: Sequence[DeveloperBranchWorkflowIssue]) -> str:
    """Format branch workflow validation issues for logs and exceptions."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", slug).strip("-")


def _require_text(issues: list[DeveloperBranchWorkflowIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(DeveloperBranchWorkflowIssue(field=field, message="Value is required."))


def _require_stack_text(blockers: list[str], field: str, value: str) -> None:
    if not value.strip():
        blockers.append(f"{field} is required for stacked branch planning.")


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()
