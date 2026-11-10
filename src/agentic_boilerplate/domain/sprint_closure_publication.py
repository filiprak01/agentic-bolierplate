"""Sprint closure and retro publication planning for Release Manager."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.story_backed_change_policy import (
    StoryBackedChangeSurface,
    build_process_change_branch_name,
    build_story_backed_change_policy_decision,
)


class SprintClosureArtifactType(str, Enum):
    """Sprint-end artifacts that can be published under a closure task."""

    RETRO_NOTE = "retro-note"
    CLOSURE_NOTE = "closure-note"
    SPRINT_PERFORMANCE = "sprint-performance"
    REGRESSION_RESULT = "regression-result"
    PROCESS_NOTE = "process-note"


class SprintClosureChangeAction(str, Enum):
    """Action required for one changed file during closure publication."""

    PUBLISH_UNDER_TASK = "publish-under-task"
    REQUIRES_STORY = "requires-story"
    PARK_LOCAL_NOTE = "park-local-note"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SprintClosureArtifact:
    """One closure artifact such as a retro note or sprint performance record."""

    path: str
    artifact_type: SprintClosureArtifactType
    title: str = ""
    jira_issue_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class SprintClosureFileChange:
    """One repo file changed as part of closure publication."""

    path: str
    change_surface: StoryBackedChangeSurface
    jira_issue_key: str = ""
    parked_by_po: bool = False


@dataclass(frozen=True)
class SprintClosureFileDecision:
    """Publication or backlog-routing decision for one changed file."""

    path: str
    change_surface: StoryBackedChangeSurface
    action: SprintClosureChangeAction
    jira_issue_key: str = ""
    validation_steps: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SprintClosurePublicationPlan:
    """Board-visible Sprint closure publication plan."""

    sprint_name: str
    publication_issue_key: str
    branch_name: str
    retro_note_path: str
    closure_note_path: str
    sprint_performance_path: str
    regression_result_summary: str
    po_acceptance_summary: str
    sprint_fit_summary: str
    follow_up_story_keys: tuple[str, ...]
    file_decisions: tuple[SprintClosureFileDecision, ...]
    warnings: tuple["SprintClosurePublicationWarning", ...]

    @property
    def ready_for_publication(self) -> bool:
        return not self.warnings


@dataclass(frozen=True)
class SprintClosurePublicationWarning:
    """Warning emitted when closure publication inputs are incomplete."""

    warning_type: str
    message: str


@dataclass(frozen=True)
class SprintClosurePublicationIssue:
    """Validation issue for sprint closure publication planning."""

    field: str
    message: str


class SprintClosurePublicationError(ValueError):
    """Raised when closure publication input is incomplete."""

    def __init__(self, issues: Sequence[SprintClosurePublicationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_sprint_closure_publication_issues(self.issues))


def build_sprint_closure_publication_plan(
    *,
    sprint_name: str,
    publication_issue_key: str,
    retro_note_path: str,
    closure_note_path: str,
    sprint_performance_path: str,
    regression_result_summary: str,
    po_acceptance_summary: str,
    sprint_fit_summary: str,
    follow_up_story_keys: tuple[str, ...] = (),
    changed_files: tuple[SprintClosureFileChange, ...] = (),
    branch_slug: str = "closure-publication",
) -> SprintClosurePublicationPlan:
    """Build a dry-run closure publication plan for Sprint 11."""

    issues: list[SprintClosurePublicationIssue] = []
    _require_text(issues, "sprint_name", sprint_name)
    _require_text(issues, "publication_issue_key", publication_issue_key)
    _require_text(issues, "retro_note_path", retro_note_path)
    _require_text(issues, "closure_note_path", closure_note_path)
    _require_text(issues, "sprint_performance_path", sprint_performance_path)
    if issues:
        raise SprintClosurePublicationError(issues)

    file_decisions = tuple(_decide_file_change(change) for change in changed_files)
    warnings = _build_warnings(
        retro_note_path=retro_note_path,
        closure_note_path=closure_note_path,
        sprint_performance_path=sprint_performance_path,
        regression_result_summary=regression_result_summary,
        po_acceptance_summary=po_acceptance_summary,
        sprint_fit_summary=sprint_fit_summary,
        file_decisions=file_decisions,
    )
    return SprintClosurePublicationPlan(
        sprint_name=sprint_name.strip(),
        publication_issue_key=publication_issue_key.strip(),
        branch_name=build_process_change_branch_name(
            jira_issue_key=publication_issue_key,
            slug=branch_slug,
        ),
        retro_note_path=retro_note_path.strip(),
        closure_note_path=closure_note_path.strip(),
        sprint_performance_path=sprint_performance_path.strip(),
        regression_result_summary=regression_result_summary.strip(),
        po_acceptance_summary=po_acceptance_summary.strip(),
        sprint_fit_summary=sprint_fit_summary.strip(),
        follow_up_story_keys=tuple(key.strip() for key in follow_up_story_keys if key.strip()),
        file_decisions=file_decisions,
        warnings=warnings,
    )


def render_sprint_closure_publication_plan(plan: SprintClosurePublicationPlan) -> str:
    """Render a durable Markdown summary for Jira comments or local evidence."""

    _validate_plan(plan)
    lines = [
        f"Sprint: {plan.sprint_name}",
        f"Publication task: {plan.publication_issue_key}",
        f"Branch: {plan.branch_name}",
        f"Ready for publication: {'yes' if plan.ready_for_publication else 'no'}",
        "",
        "Artifacts:",
        f"- retro-note: {plan.retro_note_path}",
        f"- closure-note: {plan.closure_note_path}",
        f"- sprint-performance: {plan.sprint_performance_path}",
        "",
        "Summaries:",
        f"- Regression result: {plan.regression_result_summary}",
        f"- PO acceptance: {plan.po_acceptance_summary}",
        f"- Sprint fit: {plan.sprint_fit_summary}",
    ]
    if plan.follow_up_story_keys:
        lines.extend(["", "Follow-up stories:"])
        for key in plan.follow_up_story_keys:
            lines.append(f"- {key}")
    if plan.file_decisions:
        lines.extend(["", "Changed file decisions:"])
        for decision in plan.file_decisions:
            jira_suffix = f" [{decision.jira_issue_key}]" if decision.jira_issue_key else ""
            lines.append(f"- {decision.path}: {decision.action.value}{jira_suffix} - {decision.reason}")
    if plan.warnings:
        lines.extend(["", "Warnings:"])
        for warning in plan.warnings:
            lines.append(f"- {warning.message}")
    return "\n".join(lines).strip()


def render_sprint_closure_publication_jira_comment(plan: SprintClosurePublicationPlan) -> str:
    """Render a Jira-ready summary for the closure publication task."""

    _validate_plan(plan)
    lines = [
        f"Sprint closure publication prepared for {plan.sprint_name}.",
        f"Publication task: {plan.publication_issue_key}",
        f"Branch: {plan.branch_name}",
        f"Ready for publication: {'yes' if plan.ready_for_publication else 'no'}",
    ]
    if plan.follow_up_story_keys:
        lines.append(f"Follow-up stories: {', '.join(plan.follow_up_story_keys)}")
    if plan.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning.message}" for warning in plan.warnings)
    return "\n".join(lines).strip()


def format_sprint_closure_publication_issues(issues: Sequence[SprintClosurePublicationIssue]) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _decide_file_change(change: SprintClosureFileChange) -> SprintClosureFileDecision:
    if change.parked_by_po:
        return SprintClosureFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintClosureChangeAction.PARK_LOCAL_NOTE,
            reason="Product Owner explicitly parked this file outside closure publication scope.",
        )
    policy = build_story_backed_change_policy_decision(change.change_surface)
    issue_key = change.jira_issue_key.strip()
    if policy.jira_story_required and not issue_key:
        return SprintClosureFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintClosureChangeAction.BLOCKED,
            validation_steps=policy.validation_steps,
            reason="Boilerplate behavior, code, automation, scripts, tests, or config changes require a Jira story before branch creation.",
        )
    if policy.jira_story_required:
        return SprintClosureFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintClosureChangeAction.REQUIRES_STORY,
            jira_issue_key=issue_key,
            validation_steps=policy.validation_steps,
            reason="Implement under the referenced backlog story, not under the closure task.",
        )
    return SprintClosureFileDecision(
        path=change.path.strip(),
        change_surface=change.change_surface,
        action=SprintClosureChangeAction.PUBLISH_UNDER_TASK,
        jira_issue_key=issue_key,
        validation_steps=policy.validation_steps,
        reason="Current-project documentation/process artifact can be published under the closure task.",
    )


def _build_warnings(
    *,
    retro_note_path: str,
    closure_note_path: str,
    sprint_performance_path: str,
    regression_result_summary: str,
    po_acceptance_summary: str,
    sprint_fit_summary: str,
    file_decisions: tuple[SprintClosureFileDecision, ...],
) -> tuple[SprintClosurePublicationWarning, ...]:
    warnings: list[SprintClosurePublicationWarning] = []
    if not retro_note_path.strip():
        warnings.append(SprintClosurePublicationWarning("missing-retro-note", "Retro note path was not provided."))
    if not closure_note_path.strip():
        warnings.append(SprintClosurePublicationWarning("missing-closure-note", "Closure note path was not provided."))
    if not sprint_performance_path.strip():
        warnings.append(SprintClosurePublicationWarning("missing-performance", "Sprint performance path was not provided."))
    if not regression_result_summary.strip():
        warnings.append(SprintClosurePublicationWarning("missing-regression-result", "Regression result summary was not provided."))
    if not po_acceptance_summary.strip():
        warnings.append(SprintClosurePublicationWarning("missing-po-acceptance", "PO acceptance summary was not provided."))
    if not sprint_fit_summary.strip():
        warnings.append(SprintClosurePublicationWarning("missing-sprint-fit", "Sprint fit summary was not provided."))
    if any(decision.action is SprintClosureChangeAction.BLOCKED for decision in file_decisions):
        warnings.append(SprintClosurePublicationWarning("blocked-files", "One or more changed files require a separate Jira story."))
    return tuple(warnings)


def _validate_plan(plan: SprintClosurePublicationPlan) -> None:
    issues: list[SprintClosurePublicationIssue] = []
    _require_text(issues, "sprint_name", plan.sprint_name)
    _require_text(issues, "publication_issue_key", plan.publication_issue_key)
    _require_text(issues, "retro_note_path", plan.retro_note_path)
    _require_text(issues, "closure_note_path", plan.closure_note_path)
    _require_text(issues, "sprint_performance_path", plan.sprint_performance_path)
    _require_text(issues, "regression_result_summary", plan.regression_result_summary)
    _require_text(issues, "po_acceptance_summary", plan.po_acceptance_summary)
    _require_text(issues, "sprint_fit_summary", plan.sprint_fit_summary)
    if issues:
        raise SprintClosurePublicationError(issues)


def _require_text(issues: list[SprintClosurePublicationIssue], field: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        issues.append(SprintClosurePublicationIssue(field, "Value is required."))
    return normalized
