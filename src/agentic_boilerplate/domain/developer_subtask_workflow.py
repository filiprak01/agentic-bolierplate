"""Developer subtask planning workflow."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxStatus,
    POInboxItem,
)
from agentic_boilerplate.integrations.jira import JiraIssueFields
from agentic_boilerplate.integrations.jira import JiraProjectIssueAdapter


class DeveloperSubtaskStatus(str, Enum):
    """Developer-owned subtask workflow states."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"
    DONE = "done"


TERMINAL_DEVELOPER_SUBTASK_STATUSES: frozenset[DeveloperSubtaskStatus] = frozenset(
    {DeveloperSubtaskStatus.DONE}
)


@dataclass(frozen=True)
class DeveloperSubtaskStage:
    """One visible developer implementation stage under a story or bug."""

    stage_id: str
    title: str
    description: str
    expected_changes: tuple[str, ...] = ()
    validation_commands: tuple[str, ...] = ()
    jira_subtask_key: str = ""
    status: DeveloperSubtaskStatus = DeveloperSubtaskStatus.PLANNED


@dataclass(frozen=True)
class DeveloperSubtaskPlan:
    """Subtask plan created before implementation starts."""

    parent_issue_key: str
    parent_issue_type: str
    created_at: str
    stages: tuple[DeveloperSubtaskStage, ...]
    context_pack_path: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    agent_id: str = ""


@dataclass(frozen=True)
class DeveloperSubtaskCompletion:
    """Evidence note for one completed implementation stage."""

    stage: DeveloperSubtaskStage
    commit_sha: str
    changed_files: tuple[str, ...]
    validation_results: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class DeveloperSubtaskCreatedIssue:
    """Mapping from a developer stage to its created Jira subtask."""

    stage_id: str
    jira_subtask_key: str
    summary: str


@dataclass(frozen=True)
class DeveloperSubtaskCreationResult:
    """Result of creating Jira subtasks for a developer plan."""

    parent_issue_key: str
    created_issues: tuple[DeveloperSubtaskCreatedIssue, ...]
    plan_with_keys: DeveloperSubtaskPlan


@dataclass(frozen=True)
class DeveloperSubtaskWorkflowIssue:
    """Validation issue for a developer subtask plan."""

    field: str
    message: str


class DeveloperSubtaskWorkflowError(ValueError):
    """Raised when a developer subtask workflow artifact is invalid."""

    def __init__(self, issues: Sequence[DeveloperSubtaskWorkflowIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_developer_subtask_workflow_issues(self.issues))


def build_developer_subtask_plan(
    *,
    parent_issue_key: str,
    parent_issue_type: str,
    created_at: str,
    stages: Sequence[DeveloperSubtaskStage],
    context_pack_path: str = "",
    acceptance_criteria: Sequence[str] = (),
    agent_id: str = "",
) -> DeveloperSubtaskPlan:
    """Build and validate a developer subtask plan."""

    plan = DeveloperSubtaskPlan(
        parent_issue_key=parent_issue_key,
        parent_issue_type=parent_issue_type,
        created_at=created_at,
        stages=tuple(stages),
        context_pack_path=context_pack_path,
        acceptance_criteria=tuple(_clean_items(acceptance_criteria)),
        agent_id=agent_id,
    )
    return require_valid_developer_subtask_plan(plan)


def validate_developer_subtask_plan(plan: DeveloperSubtaskPlan) -> list[DeveloperSubtaskWorkflowIssue]:
    """Return validation issues without mutating the plan."""

    issues: list[DeveloperSubtaskWorkflowIssue] = []
    _require_text(issues, "parent_issue_key", plan.parent_issue_key)
    _require_text(issues, "parent_issue_type", plan.parent_issue_type)
    _require_text(issues, "created_at", plan.created_at)

    if plan.parent_issue_type.strip().lower() not in {"story", "bug"}:
        issues.append(
            DeveloperSubtaskWorkflowIssue(
                field="parent_issue_type",
                message="Developer subtask plans must be attached to a Story or Bug.",
            )
        )

    if not plan.stages:
        issues.append(DeveloperSubtaskWorkflowIssue(field="stages", message="At least one subtask stage is required."))

    stage_ids = [stage.stage_id for stage in plan.stages]
    if len(set(stage_ids)) != len(stage_ids):
        issues.append(DeveloperSubtaskWorkflowIssue(field="stages", message="Stage IDs must be unique."))

    active_count = sum(1 for stage in plan.stages if stage.status == DeveloperSubtaskStatus.IN_PROGRESS)
    if active_count > 1:
        issues.append(
            DeveloperSubtaskWorkflowIssue(
                field="stages",
                message="Only one developer subtask stage can be in progress at a time.",
            )
        )

    for index, stage in enumerate(plan.stages):
        _require_text(issues, f"stages[{index}].stage_id", stage.stage_id)
        _require_text(issues, f"stages[{index}].title", stage.title)
        _require_text(issues, f"stages[{index}].description", stage.description)

    return issues


def require_valid_developer_subtask_plan(plan: DeveloperSubtaskPlan) -> DeveloperSubtaskPlan:
    """Raise when a developer subtask plan violates workflow rules."""

    issues = validate_developer_subtask_plan(plan)
    if issues:
        raise DeveloperSubtaskWorkflowError(issues)
    return plan


def active_developer_subtask_stage(plan: DeveloperSubtaskPlan) -> DeveloperSubtaskStage | None:
    """Return the current stage the developer should work on next."""

    explicit_active = [stage for stage in plan.stages if stage.status == DeveloperSubtaskStatus.IN_PROGRESS]
    if explicit_active:
        return explicit_active[0]
    for stage in plan.stages:
        if stage.status not in TERMINAL_DEVELOPER_SUBTASK_STATUSES:
            return stage
    return None


def jira_subtask_fields_for_stage(
    plan: DeveloperSubtaskPlan,
    stage: DeveloperSubtaskStage,
    *,
    subtask_issue_type: str = "Subtask",
    labels: Sequence[str] = (),
) -> JiraIssueFields:
    """Convert one implementation stage into Jira subtask creation fields."""

    description = render_developer_subtask_description(plan, stage)
    stage_labels = tuple(dict.fromkeys(("developer-subtask", *labels)))
    return JiraIssueFields(
        summary=f"{plan.parent_issue_key} - {stage.title}",
        issue_type=subtask_issue_type,
        description=description,
        labels=stage_labels,
        parent_key=plan.parent_issue_key,
    )


def jira_subtask_fields_for_plan(
    plan: DeveloperSubtaskPlan,
    *,
    subtask_issue_type: str = "Subtask",
    labels: Sequence[str] = (),
) -> tuple[JiraIssueFields, ...]:
    """Convert all implementation stages into Jira subtask creation fields."""

    return tuple(
        jira_subtask_fields_for_stage(
            plan,
            stage,
            subtask_issue_type=subtask_issue_type,
            labels=labels,
        )
        for stage in plan.stages
    )


def execute_developer_subtask_creation(
    adapter: JiraProjectIssueAdapter,
    plan: DeveloperSubtaskPlan,
    *,
    subtask_issue_type: str = "",
    labels: Sequence[str] = (),
) -> DeveloperSubtaskCreationResult:
    """Create Jira subtasks for every stage and return the keyed plan."""

    issue_type = subtask_issue_type or adapter.config.subtask_issue_type
    created: list[DeveloperSubtaskCreatedIssue] = []
    stages_with_keys: list[DeveloperSubtaskStage] = []
    for stage in plan.stages:
        if stage.jira_subtask_key:
            jira_subtask_key = stage.jira_subtask_key
            summary = f"{plan.parent_issue_key} - {stage.title}"
        else:
            fields = jira_subtask_fields_for_stage(
                plan,
                stage,
                subtask_issue_type=issue_type,
                labels=labels,
            )
            issue = adapter.create_issue(fields)
            jira_subtask_key = issue.key
            summary = issue.summary
        created.append(
            DeveloperSubtaskCreatedIssue(
                stage_id=stage.stage_id,
                jira_subtask_key=jira_subtask_key,
                summary=summary,
            )
        )
        stages_with_keys.append(
            DeveloperSubtaskStage(
                stage_id=stage.stage_id,
                title=stage.title,
                description=stage.description,
                expected_changes=stage.expected_changes,
                validation_commands=stage.validation_commands,
                jira_subtask_key=jira_subtask_key,
                status=stage.status,
            )
        )
    keyed_plan = DeveloperSubtaskPlan(
        parent_issue_key=plan.parent_issue_key,
        parent_issue_type=plan.parent_issue_type,
        created_at=plan.created_at,
        stages=tuple(stages_with_keys),
        context_pack_path=plan.context_pack_path,
        acceptance_criteria=plan.acceptance_criteria,
        agent_id=plan.agent_id,
    )
    return DeveloperSubtaskCreationResult(
        parent_issue_key=plan.parent_issue_key,
        created_issues=tuple(created),
        plan_with_keys=keyed_plan,
    )


def render_developer_subtask_description(plan: DeveloperSubtaskPlan, stage: DeveloperSubtaskStage) -> str:
    """Render a durable Jira description for one developer subtask."""

    sections = [
        f"Parent issue: {plan.parent_issue_key}",
        f"Stage: {stage.stage_id}",
        "",
        stage.description,
    ]
    if plan.context_pack_path:
        sections.extend(["", f"Context pack: {plan.context_pack_path}"])
    if stage.expected_changes:
        sections.extend(["", "Expected changes:", *_markdown_list(stage.expected_changes)])
    if stage.validation_commands:
        sections.extend(["", "Developer validation:", *_markdown_list(stage.validation_commands)])
    return "\n".join(sections).strip()


def render_developer_subtask_plan_summary(plan: DeveloperSubtaskPlan) -> str:
    """Render a Jira story note that shows subtask progress and next stage."""

    active_stage = active_developer_subtask_stage(plan)
    lines = [
        f"Developer subtask plan for {plan.parent_issue_key}",
        "",
        "Stages:",
    ]
    for stage in plan.stages:
        key = f" ({stage.jira_subtask_key})" if stage.jira_subtask_key else ""
        lines.append(f"- {stage.stage_id}{key}: {stage.title} [{stage.status.value}]")
    lines.extend(
        [
            "",
            "Next developer stage: "
            + (f"{active_stage.stage_id} - {active_stage.title}" if active_stage else "none"),
        ]
    )
    return "\n".join(lines).strip()


def render_developer_subtask_completion_note(completion: DeveloperSubtaskCompletion) -> str:
    """Render the Jira update note for a completed implementation stage."""

    lines = [
        f"Developer stage completed: {completion.stage.stage_id} - {completion.stage.title}",
        "",
        f"Commit: {completion.commit_sha}",
    ]
    if completion.changed_files:
        lines.extend(["", "Changed files:", *_markdown_list(completion.changed_files)])
    if completion.validation_results:
        lines.extend(["", "Validation:", *_markdown_list(completion.validation_results)])
    if completion.notes:
        lines.extend(["", "Notes:", completion.notes])
    return "\n".join(lines).strip()


def build_missing_developer_subtask_context_questions(plan: DeveloperSubtaskPlan) -> tuple[POInboxItem, ...]:
    """Create PO questions for missing context that would make implementation unsafe."""

    questions: list[POInboxItem] = []
    missing_parts: list[str] = []
    if not plan.context_pack_path:
        missing_parts.append("context pack")
    if not plan.acceptance_criteria:
        missing_parts.append("acceptance criteria")
    if not any(stage.validation_commands for stage in plan.stages):
        missing_parts.append("developer validation commands")

    for part in missing_parts:
        questions.append(
            POInboxItem(
                id=f"{plan.parent_issue_key.lower()}-developer-subtask-{part.replace(' ', '-')}",
                message_type=InboxMessageType.BLOCKING_QUESTION,
                status=InboxStatus.OPEN,
                title=f"Missing {part} for {plan.parent_issue_key}",
                message=(
                    f"The Developer Agent needs the {part} before starting implementation for "
                    f"{plan.parent_issue_key}."
                ),
                agent_role=AgentRole.DEVELOPER,
                created_at=plan.created_at,
                agent_id=plan.agent_id,
                jira_issue_key=plan.parent_issue_key,
                context_pack_path=plan.context_pack_path,
                business_impact="Implementation may proceed with incorrect scope or unverifiable results.",
                recommendation=f"Add the missing {part} to the story or context pack before work starts.",
            )
        )
    return tuple(questions)


def format_developer_subtask_workflow_issues(
    issues: Sequence[DeveloperSubtaskWorkflowIssue],
) -> str:
    """Format workflow validation issues for logs and exceptions."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _markdown_list(items: Iterable[str]) -> list[str]:
    return [f"- {item}" for item in _clean_items(items)]


def _clean_items(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(item.strip() for item in items if item.strip())


def _require_text(issues: list[DeveloperSubtaskWorkflowIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(DeveloperSubtaskWorkflowIssue(field=field, message="Value is required."))
