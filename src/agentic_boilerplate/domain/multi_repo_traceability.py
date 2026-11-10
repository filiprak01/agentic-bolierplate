"""Multi-repository Jira and GitHub traceability policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RepositoryTraceabilityRole(str, Enum):
    """Repository lanes that may be touched by one Jira story."""

    TARGET_IMPLEMENTATION = "target-implementation"
    BOILERPLATE_PROCESS = "boilerplate-process"
    DOCUMENTATION = "documentation"
    AUTOMATION = "automation"


class TraceabilityIssueKind(str, Enum):
    """Reasons a multi-repo work trace is not visible enough."""

    MISSING_REPOSITORY = "missing_repository"
    MISSING_BRANCH_JIRA_KEY = "missing_branch_jira_key"
    MISSING_COMMIT_JIRA_KEY = "missing_commit_jira_key"
    MISSING_PR_TITLE_JIRA_KEY = "missing_pr_title_jira_key"
    MISSING_PR_BODY_JIRA_KEY = "missing_pr_body_jira_key"
    MISSING_MANUAL_JIRA_PR_LINK = "missing_manual_jira_pr_link"
    MISSING_PROCESS_CHANGE_REASON = "missing_process_change_reason"
    MISSING_MULTI_REPO_REASON = "missing_multi_repo_reason"


@dataclass(frozen=True)
class RepositoryTraceabilityTarget:
    """One configured repository lane for a project."""

    role: RepositoryTraceabilityRole
    repository: str = ""
    default_branch: str = "main"
    jira_development_panel_expected: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.repository.strip())


@dataclass(frozen=True)
class RepositoryWorkTrace:
    """Traceability metadata for one repository touched by a Jira issue."""

    target: RepositoryTraceabilityTarget
    branch_name: str
    commit_messages: tuple[str, ...]
    pull_request_title: str
    pull_request_body: str
    pull_request_url: str = ""
    manual_jira_pr_link_comment: str = ""
    process_change_reason: str = ""


@dataclass(frozen=True)
class TraceabilityIssue:
    """One machine-readable traceability policy issue."""

    kind: TraceabilityIssueKind
    repository_role: RepositoryTraceabilityRole
    message: str


@dataclass(frozen=True)
class MultiRepoTraceabilityDecision:
    """Pass/fail decision for one Jira issue across repository lanes."""

    jira_issue_key: str
    passed: bool
    issues: tuple[TraceabilityIssue, ...]
    warnings: tuple[str, ...]


def validate_multi_repo_traceability(
    *,
    jira_issue_key: str,
    traces: tuple[RepositoryWorkTrace, ...],
    multi_repo_reason: str = "",
) -> MultiRepoTraceabilityDecision:
    """Validate that all affected repositories keep Jira/GitHub lineage visible."""

    normalized_key = jira_issue_key.strip()
    issues: list[TraceabilityIssue] = []
    warnings: list[str] = []
    configured_traces = tuple(trace for trace in traces if trace.target.is_configured)
    if len(configured_traces) > 1 and not multi_repo_reason.strip():
        for trace in configured_traces:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_MULTI_REPO_REASON,
                    trace.target.role,
                    "Multi-repo work requires visible reasoning in the story and PRs.",
                )
            )

    for trace in traces:
        target = trace.target
        if not target.is_configured:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_REPOSITORY,
                    target.role,
                    "Affected repository lane is missing a configured owner/name repository.",
                )
            )
            continue
        if normalized_key and normalized_key not in trace.branch_name:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_BRANCH_JIRA_KEY,
                    target.role,
                    "Branch name must include the Jira issue key.",
                )
            )
        if not trace.commit_messages:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_COMMIT_JIRA_KEY,
                    target.role,
                    "At least one commit message is required for the affected repository.",
                )
            )
        for commit_message in trace.commit_messages:
            if normalized_key and normalized_key not in commit_message:
                issues.append(
                    _issue(
                        TraceabilityIssueKind.MISSING_COMMIT_JIRA_KEY,
                        target.role,
                        "Every commit message must include the Jira issue key.",
                    )
                )
        if normalized_key and normalized_key not in trace.pull_request_title:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_PR_TITLE_JIRA_KEY,
                    target.role,
                    "Pull request title must include the Jira issue key.",
                )
            )
        if normalized_key and normalized_key not in trace.pull_request_body:
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_PR_BODY_JIRA_KEY,
                    target.role,
                    "Pull request body must include the Jira issue key and affected repository role.",
                )
            )
        if not target.jira_development_panel_expected:
            warnings.append(
                f"{target.role.value}: Jira development panel visibility is not expected for {target.repository}; "
                "write an explicit Jira PR link comment."
            )
            if not trace.manual_jira_pr_link_comment.strip() and not trace.pull_request_url.strip():
                issues.append(
                    _issue(
                        TraceabilityIssueKind.MISSING_MANUAL_JIRA_PR_LINK,
                        target.role,
                        "Manual Jira PR link is required when automatic Jira development-panel visibility is not expected.",
                    )
                )
        if target.role == RepositoryTraceabilityRole.BOILERPLATE_PROCESS and not trace.process_change_reason.strip():
            issues.append(
                _issue(
                    TraceabilityIssueKind.MISSING_PROCESS_CHANGE_REASON,
                    target.role,
                    "Boilerplate/process repository changes must state the project story reason.",
                )
            )

    return MultiRepoTraceabilityDecision(
        jira_issue_key=normalized_key,
        passed=not issues,
        issues=tuple(issues),
        warnings=tuple(warnings),
    )


def render_expected_repository_section(targets: tuple[RepositoryTraceabilityTarget, ...]) -> str:
    """Render a Jira description section listing expected repository lanes."""

    lines = ["Expected Repositories:"]
    for target in targets:
        repository = target.repository.strip() or "TBD"
        visibility = "yes" if target.jira_development_panel_expected else "no"
        lines.append(
            f"- {target.role.value}: {repository} "
            f"(default branch: {target.default_branch or 'main'}, Jira development panel expected: {visibility})"
        )
    return "\n".join(lines)


def render_manual_multi_repo_pr_link_comment(
    *,
    jira_issue_key: str,
    trace: RepositoryWorkTrace,
) -> str:
    """Render the Jira fallback comment for one affected repository PR."""

    lines = [
        f"Manual repository PR link for {jira_issue_key.strip()}.",
        "",
        f"Repository role: {trace.target.role.value}",
        f"Repository: {trace.target.repository or 'TBD'}",
        f"Branch: {trace.branch_name}",
        f"PR: {trace.pull_request_url or 'TBD'}",
        "",
        "Commits:",
    ]
    lines.extend(f"- {message}" for message in trace.commit_messages)
    if trace.process_change_reason.strip():
        lines.extend(["", f"Process/change reason: {trace.process_change_reason.strip()}"])
    return "\n".join(lines).strip()


def build_jira_development_panel_warnings(
    targets: tuple[RepositoryTraceabilityTarget, ...],
) -> tuple[str, ...]:
    """Return setup diagnostic warnings for repositories needing manual PR links."""

    return tuple(
        f"{target.role.value}: {target.repository} will require explicit Jira PR links."
        for target in targets
        if target.is_configured and not target.jira_development_panel_expected
    )


def _issue(
    kind: TraceabilityIssueKind,
    role: RepositoryTraceabilityRole,
    message: str,
) -> TraceabilityIssue:
    return TraceabilityIssue(kind=kind, repository_role=role, message=message)
