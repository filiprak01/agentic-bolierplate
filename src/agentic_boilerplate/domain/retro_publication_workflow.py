"""Sprint retro and post-mortem publication workflow planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.story_backed_change_policy import (
    StoryBackedChangeSurface,
    build_process_change_branch_name,
    build_story_backed_change_policy_decision,
)


class SprintPublicationArtifactType(str, Enum):
    """Sprint-end artifacts that can be published under a publication task."""

    RETRO = "retro"
    POST_MORTEM = "post-mortem"
    CLOSURE = "closure"
    SPRINT_PERFORMANCE = "sprint-performance"
    PROCESS_NOTE = "process-note"


class SprintPublicationTaskAction(str, Enum):
    """How the sprint publication task should be handled."""

    DETECT_EXISTING = "detect-existing"
    CREATE = "create"


class SprintPublicationChangeAction(str, Enum):
    """Action required for one changed file after retro."""

    PUBLISH_UNDER_TASK = "publish-under-task"
    REQUIRES_STORY = "requires-story"
    PARK_LOCAL_NOTE = "park-local-note"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SprintPublicationArtifact:
    """One retro, post-mortem, closure, or process-note artifact."""

    path: str
    artifact_type: SprintPublicationArtifactType
    title: str = ""
    jira_issue_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class SprintPublicationFileChange:
    """One repo file changed after retro or closure preparation."""

    path: str
    change_surface: StoryBackedChangeSurface
    jira_issue_key: str = ""
    parked_by_po: bool = False


@dataclass(frozen=True)
class SprintPublicationFileDecision:
    """Publication or backlog-routing decision for one changed file."""

    path: str
    change_surface: StoryBackedChangeSurface
    action: SprintPublicationChangeAction
    jira_issue_key: str = ""
    validation_steps: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SprintPublicationPlan:
    """Publication plan used before a sprint can be closed or the next sprint starts."""

    sprint_name: str
    publication_issue_key: str
    task_action: SprintPublicationTaskAction
    branch_name: str
    artifacts: tuple[SprintPublicationArtifact, ...]
    file_decisions: tuple[SprintPublicationFileDecision, ...]
    follow_up_story_keys: tuple[str, ...]
    pull_request_urls: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    blocked_reasons: tuple[str, ...]

    @property
    def next_sprint_blocked(self) -> bool:
        return bool(self.blocked_reasons)


@dataclass(frozen=True)
class SprintPublicationIssue:
    """Validation issue for retro publication workflow inputs."""

    field: str
    message: str


class SprintPublicationWorkflowError(ValueError):
    """Raised when sprint publication workflow input is incomplete."""

    def __init__(self, issues: Sequence[SprintPublicationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_sprint_publication_issues(self.issues))


@dataclass(frozen=True)
class SprintRetroSetupTask:
    """Board-visible sprint support task used to collect retro input."""

    issue_key: str
    summary: str
    status: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class SprintRetroSetupValidationResult:
    """Retro setup readiness check before delivery work begins."""

    sprint_name: str
    retro_intake_task: SprintRetroSetupTask | None
    retro_template_path: str
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def build_sprint_publication_plan(
    *,
    sprint_name: str,
    artifacts: tuple[SprintPublicationArtifact, ...],
    changed_files: tuple[SprintPublicationFileChange, ...] = (),
    publication_issue_key: str = "",
    follow_up_story_keys: tuple[str, ...] = (),
    pull_request_urls: tuple[str, ...] = (),
    evidence_paths: tuple[str, ...] = (),
    branch_slug: str = "retro-publication",
) -> SprintPublicationPlan:
    """Build a dry-run publication plan for sprint retro and closure artifacts."""

    issues: list[SprintPublicationIssue] = []
    _require_text(issues, "sprint_name", sprint_name)
    if not artifacts:
        issues.append(SprintPublicationIssue("artifacts", "At least one sprint publication artifact is required."))
    for index, artifact in enumerate(artifacts):
        _require_text(issues, f"artifacts[{index}].path", artifact.path)
    for index, change in enumerate(changed_files):
        _require_text(issues, f"changed_files[{index}].path", change.path)
    if issues:
        raise SprintPublicationWorkflowError(issues)

    normalized_issue = publication_issue_key.strip()
    task_action = SprintPublicationTaskAction.DETECT_EXISTING if normalized_issue else SprintPublicationTaskAction.CREATE
    file_decisions = tuple(_decide_file_change(change) for change in changed_files)
    blocked_reasons = _blocked_reasons(
        artifacts=artifacts,
        file_decisions=file_decisions,
        publication_issue_key=normalized_issue,
    )
    return SprintPublicationPlan(
        sprint_name=sprint_name.strip(),
        publication_issue_key=normalized_issue,
        task_action=task_action,
        branch_name=build_process_change_branch_name(
            jira_issue_key=normalized_issue,
            sprint_name="" if normalized_issue else sprint_name,
            slug=branch_slug,
        ),
        artifacts=tuple(_normalize_artifact(artifact) for artifact in artifacts),
        file_decisions=file_decisions,
        follow_up_story_keys=tuple(key.strip() for key in follow_up_story_keys if key.strip()),
        pull_request_urls=tuple(url.strip() for url in pull_request_urls if url.strip()),
        evidence_paths=tuple(path.strip() for path in evidence_paths if path.strip()),
        blocked_reasons=blocked_reasons,
    )


def render_sprint_publication_plan(plan: SprintPublicationPlan) -> str:
    """Render a durable Markdown summary for Jira comments or local evidence."""

    lines = [
        f"Sprint: {plan.sprint_name}",
        f"Publication task: {plan.publication_issue_key or 'create required'}",
        f"Task action: {plan.task_action.value}",
        f"Branch: {plan.branch_name}",
        f"Next sprint blocked: {'yes' if plan.next_sprint_blocked else 'no'}",
        "",
        "Artifacts:",
    ]
    for artifact in plan.artifacts:
        issue_suffix = f" ({', '.join(artifact.jira_issue_keys)})" if artifact.jira_issue_keys else ""
        lines.append(f"- {artifact.artifact_type.value}: {artifact.path}{issue_suffix}")
    if plan.file_decisions:
        lines.extend(["", "Changed file decisions:"])
        for decision in plan.file_decisions:
            jira_suffix = f" [{decision.jira_issue_key}]" if decision.jira_issue_key else ""
            lines.append(f"- {decision.path}: {decision.action.value}{jira_suffix} - {decision.reason}")
    if plan.follow_up_story_keys:
        lines.extend(["", "Follow-up stories:"])
        for key in plan.follow_up_story_keys:
            lines.append(f"- {key}")
    if plan.pull_request_urls:
        lines.extend(["", "Pull requests:"])
        for url in plan.pull_request_urls:
            lines.append(f"- {url}")
    if plan.evidence_paths:
        lines.extend(["", "Evidence paths:"])
        for path in plan.evidence_paths:
            lines.append(f"- {path}")
    if plan.blocked_reasons:
        lines.extend(["", "Blocking reasons:"])
        for reason in plan.blocked_reasons:
            lines.append(f"- {reason}")
    return "\n".join(lines).strip()


def render_sprint_publication_jira_comment(plan: SprintPublicationPlan) -> str:
    """Render the summary that should be posted to the sprint publication task."""

    lines = [
        f"Sprint publication workflow prepared for {plan.sprint_name}.",
        "",
        f"Publication branch: {plan.branch_name}",
        f"Next sprint gate: {'blocked' if plan.next_sprint_blocked else 'clear'}",
    ]
    if plan.follow_up_story_keys:
        lines.append(f"Follow-up stories: {', '.join(plan.follow_up_story_keys)}")
    if plan.pull_request_urls:
        lines.append(f"Pull requests: {', '.join(plan.pull_request_urls)}")
    if plan.evidence_paths:
        lines.append(f"Evidence paths: {', '.join(plan.evidence_paths)}")
    if plan.blocked_reasons:
        lines.append("")
        lines.append("Blocking reasons:")
        lines.extend(f"- {reason}" for reason in plan.blocked_reasons)
    return "\n".join(lines).strip()


def validate_sprint_retro_setup(
    *,
    sprint_name: str,
    support_tasks: tuple[SprintRetroSetupTask, ...],
    retro_template_path: str,
    retro_intake_labels: tuple[str, ...] = ("retro-intake",),
) -> SprintRetroSetupValidationResult:
    """Validate that sprint retro intake is visible before delivery starts."""

    normalized_sprint = sprint_name.strip()
    normalized_template = retro_template_path.strip()
    issues: list[str] = []
    if not normalized_sprint:
        issues.append("Sprint name is required for retro setup validation.")
    if not normalized_template:
        issues.append("Retro intake template path is required before delivery starts.")
    retro_task = _find_retro_intake_task(support_tasks, retro_intake_labels)
    if retro_task is None:
        issues.append("Board-visible retro intake support task is required before delivery starts.")
    return SprintRetroSetupValidationResult(
        sprint_name=normalized_sprint,
        retro_intake_task=retro_task,
        retro_template_path=normalized_template,
        issues=tuple(issues),
    )


def render_sprint_retro_setup_validation(result: SprintRetroSetupValidationResult) -> str:
    """Render a sprint setup checklist result for Jira or durable evidence."""

    lines = [
        f"Sprint: {result.sprint_name or 'unknown'}",
        f"Retro setup ready: {'yes' if result.ready else 'no'}",
        f"Retro template: {result.retro_template_path or 'missing'}",
        f"Retro intake task: {result.retro_intake_task.issue_key if result.retro_intake_task else 'missing'}",
        "",
        "Issues:",
    ]
    if result.issues:
        lines.extend(f"- {issue}" for issue in result.issues)
    else:
        lines.append("- None")
    return "\n".join(lines)


def format_sprint_publication_issues(issues: Sequence[SprintPublicationIssue]) -> str:
    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _decide_file_change(change: SprintPublicationFileChange) -> SprintPublicationFileDecision:
    if change.parked_by_po:
        return SprintPublicationFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintPublicationChangeAction.PARK_LOCAL_NOTE,
            reason="Product Owner explicitly parked this file outside sprint publication scope.",
        )
    policy = build_story_backed_change_policy_decision(change.change_surface)
    issue_key = change.jira_issue_key.strip()
    if policy.jira_story_required and not issue_key:
        return SprintPublicationFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintPublicationChangeAction.BLOCKED,
            validation_steps=policy.validation_steps,
            reason="Boilerplate behavior, code, automation, scripts, tests, or config changes require a Jira story before branch creation.",
        )
    if policy.jira_story_required:
        return SprintPublicationFileDecision(
            path=change.path.strip(),
            change_surface=change.change_surface,
            action=SprintPublicationChangeAction.REQUIRES_STORY,
            jira_issue_key=issue_key,
            validation_steps=policy.validation_steps,
            reason="Implement under the referenced backlog story, not under the sprint publication task.",
        )
    return SprintPublicationFileDecision(
        path=change.path.strip(),
        change_surface=change.change_surface,
        action=SprintPublicationChangeAction.PUBLISH_UNDER_TASK,
        jira_issue_key=issue_key,
        validation_steps=policy.validation_steps,
        reason="Current-project documentation/process artifact can be published under the sprint publication task.",
    )


def _blocked_reasons(
    *,
    artifacts: tuple[SprintPublicationArtifact, ...],
    file_decisions: tuple[SprintPublicationFileDecision, ...],
    publication_issue_key: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not publication_issue_key.strip():
        reasons.append("Sprint publication Task must be created before publication PR creation.")
    artifact_paths = {artifact.path.strip() for artifact in artifacts if artifact.path.strip()}
    for decision in file_decisions:
        if decision.action is SprintPublicationChangeAction.BLOCKED:
            reasons.append(f"{decision.path} is missing a required Jira story.")
        if decision.action is SprintPublicationChangeAction.PUBLISH_UNDER_TASK and decision.path not in artifact_paths:
            reasons.append(f"{decision.path} must be included as a publication artifact or parked by Product Owner.")
    return tuple(dict.fromkeys(reasons))


def _normalize_artifact(artifact: SprintPublicationArtifact) -> SprintPublicationArtifact:
    return SprintPublicationArtifact(
        path=artifact.path.strip(),
        artifact_type=artifact.artifact_type,
        title=artifact.title.strip(),
        jira_issue_keys=tuple(key.strip() for key in artifact.jira_issue_keys if key.strip()),
    )


def _require_text(issues: list[SprintPublicationIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(SprintPublicationIssue(field, "Value is required."))


def _find_retro_intake_task(
    support_tasks: tuple[SprintRetroSetupTask, ...],
    retro_intake_labels: tuple[str, ...],
) -> SprintRetroSetupTask | None:
    normalized_labels = {label.strip().casefold() for label in retro_intake_labels if label.strip()}
    for task in support_tasks:
        labels = {label.strip().casefold() for label in task.labels}
        if labels & normalized_labels:
            return task
        if "retro intake" in task.summary.strip().casefold():
            return task
    return None
