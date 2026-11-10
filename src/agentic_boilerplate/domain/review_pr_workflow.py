"""Review Agent pull request workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from agentic_boilerplate.domain.po_inbox import AgentRole
from agentic_boilerplate.domain.review_record import (
    ReviewDecision,
    ReviewFinding,
    ReviewFindingKind,
    ReviewFindingSeverity,
    ReviewFindingStatus,
    ReviewModelRouting,
    ReviewRecord,
    ReviewScope,
    ReviewScopeMode,
    find_repeated_review_findings,
)
from agentic_boilerplate.integrations.github import GitHubPullRequestMergeFields, GitHubPullRequestMergeResult

REVIEW_MERGED_JIRA_STATUS = "DEV COMPLETED"


class ReviewExpansionReason(str, Enum):
    """Reasons that justify expanding beyond diff-first review."""

    ARCHITECTURE = "architecture"
    SECURITY = "security"
    DATA_MODEL = "data-model"
    SHARED_CONTRACT = "shared-contract"
    DEPENDENCY_DIRECTION = "dependency-direction"
    REPEATED_FINDING = "repeated-finding"


class ReviewApprovalPublicationMode(str, Enum):
    """How Review Agent approval was published to GitHub/Jira."""

    FORMAL_REVIEW = "formal-review"
    COMMENT_FALLBACK = "comment-fallback"
    FAILED = "failed"


class StackedReviewMergeStrategy(str, Enum):
    """Merge strategy chosen for a stacked pull request layer."""

    BOTTOM_UP = "bottom-up"
    QUEUED_STACK_MERGE = "queued-stack-merge"


class StackedReviewCommentScope(str, Enum):
    """Scope for review comments on stacked pull requests."""

    LAYER_LOCAL = "layer-local"
    LOWER_LAYER_CHANGE = "lower-layer-change"


@dataclass(frozen=True)
class PullRequestReviewInput:
    """Inputs the Review Agent needs to review one pull request."""

    review_record_id: str
    jira_issue_key: str
    story_summary: str
    acceptance_criteria: tuple[str, ...]
    pull_request_url: str
    pull_request_number: int
    head_branch: str
    base_branch: str
    head_sha: str
    changed_files: tuple[str, ...]
    related_tests: tuple[str, ...]
    diff_summary: str
    direct_contracts: tuple[str, ...] = ()
    expanded_context_paths: tuple[str, ...] = ()
    expansion_reasons: tuple[ReviewExpansionReason, ...] = ()
    existing_jira_pr_link_visible: bool = True
    detected_conflicts: tuple[str, ...] = ()
    unrelated_staged_files: tuple[str, ...] = ()
    reviewer: AgentRole = AgentRole.REVIEW


@dataclass(frozen=True)
class PullRequestReviewIssue:
    """Validation or review planning issue."""

    field: str
    message: str


@dataclass(frozen=True)
class PullRequestReviewResult:
    """Review workflow output used by Review Agent orchestration."""

    review_record: ReviewRecord
    ready_to_merge: bool
    jira_comment: str
    jira_status_after_merge: str
    merge_fields: GitHubPullRequestMergeFields | None = None


@dataclass(frozen=True)
class ReviewApprovalPublicationStatus:
    """Visibility status for formal review approval and fallback publication."""

    jira_issue_key: str
    pull_request_url: str
    review_record_id: str
    mode: ReviewApprovalPublicationMode
    published: bool
    formal_review_created: bool
    fallback_comment_created: bool
    provider_status_code: int | None = None
    provider_message: str = ""
    diagnostic_summary: str = ""


@dataclass(frozen=True)
class StackedPullRequestReviewContext:
    """Review inputs that make stacked PR approval and merge order deterministic."""

    review_record_id: str
    jira_issue_key: str
    pull_request_url: str
    pull_request_number: int
    stack_id: str
    lane_id: str
    stack_layer: int
    stack_trunk: str
    head_branch: str
    base_branch: str
    expected_base_branch: str
    reviewed_base_sha: str
    reviewed_head_sha: str
    context_pack_path: str
    checks_complete: bool = True
    checks_passed: bool = True
    jira_pr_link_visible: bool = True
    stack_metadata_present: bool = True
    required_lower_layer_approved: bool = True
    required_lower_layer_merged: bool = False
    merge_queue_supported: bool = False
    branch_protection_supports_stack_merge: bool = False
    lower_layer_recorded_head_sha: str = ""
    lower_layer_current_head_sha: str = ""
    detected_conflicts: tuple[str, ...] = field(default_factory=tuple)
    layer_local_findings: tuple[str, ...] = field(default_factory=tuple)
    lower_layer_change_findings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StackedPullRequestLayerReviewRecord:
    """Durable review record metadata for one stacked PR layer."""

    review_record_id: str
    jira_issue_key: str
    pull_request_url: str
    pull_request_number: int
    stack_id: str
    lane_id: str
    stack_layer: int
    base_branch: str
    head_branch: str
    reviewed_base_sha: str
    reviewed_head_sha: str
    merge_strategy: StackedReviewMergeStrategy
    approval_ready: bool
    merge_ready: bool
    stale_rebase_required: bool


@dataclass(frozen=True)
class StackedPullRequestReviewDecision:
    """Review Agent decision for a stacked PR layer."""

    review_record: StackedPullRequestLayerReviewRecord
    approval_ready: bool
    merge_ready: bool
    merge_strategy: StackedReviewMergeStrategy
    stale_rebase_required: bool
    approval_blockers: tuple[str, ...] = field(default_factory=tuple)
    merge_blockers: tuple[str, ...] = field(default_factory=tuple)
    layer_local_comments: tuple[str, ...] = field(default_factory=tuple)
    lower_layer_change_comments: tuple[str, ...] = field(default_factory=tuple)


class PullRequestReviewWorkflowError(ValueError):
    """Raised when review workflow input is not usable."""

    def __init__(self, issues: Sequence[PullRequestReviewIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_pull_request_review_issues(self.issues))


def validate_pull_request_review_input(review_input: PullRequestReviewInput) -> list[PullRequestReviewIssue]:
    """Return input issues before review planning."""

    issues: list[PullRequestReviewIssue] = []
    _require_text(issues, "review_record_id", review_input.review_record_id)
    _require_text(issues, "jira_issue_key", review_input.jira_issue_key)
    _require_text(issues, "story_summary", review_input.story_summary)
    _require_text(issues, "pull_request_url", review_input.pull_request_url)
    _require_text(issues, "head_branch", review_input.head_branch)
    _require_text(issues, "base_branch", review_input.base_branch)
    _require_text(issues, "head_sha", review_input.head_sha)
    _require_text(issues, "diff_summary", review_input.diff_summary)
    if review_input.pull_request_number <= 0:
        issues.append(PullRequestReviewIssue("pull_request_number", "Pull request number must be positive."))
    if not review_input.acceptance_criteria:
        issues.append(PullRequestReviewIssue("acceptance_criteria", "At least one acceptance criterion is required."))
    if not review_input.changed_files:
        issues.append(PullRequestReviewIssue("changed_files", "At least one changed file is required."))
    if review_input.expanded_context_paths and not review_input.expansion_reasons:
        issues.append(
            PullRequestReviewIssue(
                "expansion_reasons",
                "Expanded context paths require at least one expansion reason.",
            )
        )
    return issues


def require_valid_pull_request_review_input(review_input: PullRequestReviewInput) -> PullRequestReviewInput:
    """Raise when review input is incomplete."""

    issues = validate_pull_request_review_input(review_input)
    if issues:
        raise PullRequestReviewWorkflowError(issues)
    return review_input


def plan_review_scope(review_input: PullRequestReviewInput) -> ReviewScope:
    """Build quota-aware review scope metadata."""

    require_valid_pull_request_review_input(review_input)
    if review_input.expansion_reasons:
        return ReviewScope(
            mode=ReviewScopeMode.EXPANDED_CONTEXT,
            changed_files=review_input.changed_files,
            related_tests=review_input.related_tests,
            touched_contracts=review_input.direct_contracts,
            expanded_context_paths=review_input.expanded_context_paths,
            expansion_reason=", ".join(reason.value for reason in review_input.expansion_reasons),
        )
    return ReviewScope(
        mode=ReviewScopeMode.DIFF_FIRST,
        changed_files=review_input.changed_files,
        related_tests=review_input.related_tests,
        touched_contracts=review_input.direct_contracts,
    )


def build_initial_review_record(
    review_input: PullRequestReviewInput,
    routing: ReviewModelRouting,
    *,
    created_at: str,
    updated_at: str,
) -> ReviewRecord:
    """Create the initial review record from PR metadata and planned scope."""

    scope = plan_review_scope(review_input)
    findings: list[ReviewFinding] = []
    for index, conflict in enumerate(review_input.detected_conflicts, start=1):
        findings.append(
            ReviewFinding(
                id=f"conflict-{index:03d}",
                title="Merge conflict blocks review",
                description=conflict,
                kind=ReviewFindingKind.CONFLICT,
                severity=ReviewFindingSeverity.BLOCKING,
            )
        )
    if not review_input.existing_jira_pr_link_visible:
        findings.append(
            ReviewFinding(
                id="jira-pr-link-001",
                title="Jira story is missing visible pull request link",
                description="Review Agent could not confirm a visible GitHub PR link on the Jira story.",
                kind=ReviewFindingKind.MAINTAINABILITY,
                severity=ReviewFindingSeverity.MEDIUM,
            )
        )
    if review_input.unrelated_staged_files:
        findings.append(
            ReviewFinding(
                id="staged-scope-001",
                title="Pull request includes unrelated staged or pushed files",
                description="Review Agent found files outside the approved story scope: "
                + ", ".join(review_input.unrelated_staged_files),
                kind=ReviewFindingKind.MAINTAINABILITY,
                severity=ReviewFindingSeverity.HIGH,
            )
        )
    return ReviewRecord(
        id=review_input.review_record_id,
        jira_issue_key=review_input.jira_issue_key,
        pull_request_url=review_input.pull_request_url,
        pull_request_number=review_input.pull_request_number,
        head_branch=review_input.head_branch,
        base_branch=review_input.base_branch,
        head_sha=review_input.head_sha,
        reviewer=review_input.reviewer,
        scope=scope,
        routing=routing,
        final_decision=ReviewDecision.PENDING,
        created_at=created_at,
        updated_at=updated_at,
        findings=tuple(findings),
    )


def repeated_findings_require_expansion(record: ReviewRecord, previous_records: Sequence[ReviewRecord]) -> bool:
    """Return whether repeated findings justify expanded review context."""

    return bool(find_repeated_review_findings(record, previous_records))


def decide_pull_request_review(
    record: ReviewRecord,
    *,
    merge_commit_title: str,
    merge_commit_message: str = "",
) -> PullRequestReviewResult:
    """Build review decision, merge readiness, and Jira visibility comment."""

    blocking_findings = tuple(
        finding
        for finding in record.findings
        if finding.status == ReviewFindingStatus.OPEN and finding.severity == ReviewFindingSeverity.BLOCKING
    )
    open_findings = tuple(finding for finding in record.findings if finding.status == ReviewFindingStatus.OPEN)
    if open_findings:
        decision = ReviewDecision.BLOCKED if blocking_findings else ReviewDecision.CHANGES_REQUESTED
        decided_record = _replace_record_decision(record, decision)
        return PullRequestReviewResult(
            review_record=decided_record,
            ready_to_merge=False,
            jira_comment=render_review_change_request_comment(decided_record),
            jira_status_after_merge="",
        )
    decided_record = _replace_record_decision(record, ReviewDecision.APPROVED)
    merge_fields = GitHubPullRequestMergeFields(
        number=record.pull_request_number,
        commit_title=merge_commit_title,
        commit_message=merge_commit_message,
        merge_method="merge",
    )
    return PullRequestReviewResult(
        review_record=decided_record,
        ready_to_merge=True,
        jira_comment=render_review_merge_ready_comment(decided_record),
        jira_status_after_merge=REVIEW_MERGED_JIRA_STATUS,
        merge_fields=merge_fields,
    )


def render_review_change_request_comment(record: ReviewRecord) -> str:
    """Render Jira comment for review findings or change requests."""

    lines = [
        f"Review completed for {record.jira_issue_key}: changes requested.",
        "",
        f"PR: {record.pull_request_url}",
        f"Review scope: {record.scope.mode.value}",
        f"Model/reasoning: {record.routing.model} / {record.routing.reasoning.value}",
        "",
        "Findings:",
    ]
    for finding in record.findings:
        if finding.status == ReviewFindingStatus.OPEN:
            lines.append(f"- {finding.id}: {finding.title} [{finding.kind.value}, {finding.severity.value}]")
    return "\n".join(lines).strip()


def render_review_merge_ready_comment(record: ReviewRecord) -> str:
    """Render Jira comment for clean review before merge."""

    return (
        f"Review completed for {record.jira_issue_key}: approved for merge.\n\n"
        f"PR: {record.pull_request_url}\n"
        f"Review scope: {record.scope.mode.value}\n"
        f"Model/reasoning: {record.routing.model} / {record.routing.reasoning.value}\n"
        f"Routing rationale: {record.routing.rationale}"
    ).strip()


def render_review_merged_comment(
    record: ReviewRecord,
    merge_result: GitHubPullRequestMergeResult,
) -> str:
    """Render Jira comment after Review Agent merges a clean PR."""

    return (
        f"Review Agent merged PR for {record.jira_issue_key}.\n\n"
        f"PR: {record.pull_request_url}\n"
        f"Merge SHA: {merge_result.sha}\n"
        f"Merge result: {merge_result.message}\n"
        f"Next Jira status: {REVIEW_MERGED_JIRA_STATUS}"
    ).strip()


def build_review_approval_publication_status(
    *,
    jira_issue_key: str,
    pull_request_url: str,
    review_record_id: str,
    formal_review_created: bool,
    fallback_comment_created: bool,
    provider_status_code: int | None = None,
    provider_message: str = "",
) -> ReviewApprovalPublicationStatus:
    """Build visible diagnostics for review approval publication."""

    if not jira_issue_key.strip():
        raise PullRequestReviewWorkflowError((PullRequestReviewIssue("jira_issue_key", "Value is required."),))
    if not pull_request_url.strip():
        raise PullRequestReviewWorkflowError((PullRequestReviewIssue("pull_request_url", "Value is required."),))
    if not review_record_id.strip():
        raise PullRequestReviewWorkflowError((PullRequestReviewIssue("review_record_id", "Value is required."),))
    if formal_review_created:
        mode = ReviewApprovalPublicationMode.FORMAL_REVIEW
        published = True
        diagnostic = "formal GitHub approval review was created"
    elif fallback_comment_created:
        mode = ReviewApprovalPublicationMode.COMMENT_FALLBACK
        published = True
        diagnostic = _fallback_diagnostic(provider_status_code, provider_message)
    else:
        mode = ReviewApprovalPublicationMode.FAILED
        published = False
        diagnostic = _fallback_diagnostic(provider_status_code, provider_message)
    return ReviewApprovalPublicationStatus(
        jira_issue_key=jira_issue_key.strip(),
        pull_request_url=pull_request_url.strip(),
        review_record_id=review_record_id.strip(),
        mode=mode,
        published=published,
        formal_review_created=formal_review_created,
        fallback_comment_created=fallback_comment_created,
        provider_status_code=provider_status_code,
        provider_message=provider_message.strip(),
        diagnostic_summary=diagnostic,
    )


def render_review_approval_publication_status(status: ReviewApprovalPublicationStatus) -> str:
    """Render approval publication diagnostics for Jira or PR comments."""

    lines = [
        f"Review approval publication status for {status.jira_issue_key}: {status.mode.value}.",
        "",
        f"PR: {status.pull_request_url}",
        f"Review record: {status.review_record_id}",
        f"Published: {'yes' if status.published else 'no'}",
        f"Formal review created: {'yes' if status.formal_review_created else 'no'}",
        f"Fallback comment created: {'yes' if status.fallback_comment_created else 'no'}",
        f"Diagnostic: {status.diagnostic_summary}",
    ]
    if status.provider_status_code is not None:
        lines.append(f"Provider status code: {status.provider_status_code}")
    if status.provider_message:
        lines.append(f"Provider message: {status.provider_message}")
    return "\n".join(lines).strip()


def validate_stacked_pull_request_review_context(
    context: StackedPullRequestReviewContext,
) -> list[PullRequestReviewIssue]:
    """Return deterministic stacked PR review input issues."""

    issues: list[PullRequestReviewIssue] = []
    _require_text(issues, "review_record_id", context.review_record_id)
    _require_text(issues, "jira_issue_key", context.jira_issue_key)
    _require_text(issues, "pull_request_url", context.pull_request_url)
    _require_text(issues, "head_branch", context.head_branch)
    _require_text(issues, "base_branch", context.base_branch)
    _require_text(issues, "expected_base_branch", context.expected_base_branch)
    _require_text(issues, "reviewed_base_sha", context.reviewed_base_sha)
    _require_text(issues, "reviewed_head_sha", context.reviewed_head_sha)
    _require_text(issues, "context_pack_path", context.context_pack_path)
    if context.pull_request_number <= 0:
        issues.append(PullRequestReviewIssue("pull_request_number", "Pull request number must be positive."))
    if not context.stack_metadata_present:
        issues.append(PullRequestReviewIssue("stack_metadata", "Stack metadata is missing."))
    _require_text(issues, "stack_id", context.stack_id)
    _require_text(issues, "lane_id", context.lane_id)
    _require_text(issues, "stack_trunk", context.stack_trunk)
    if context.stack_layer < 1:
        issues.append(PullRequestReviewIssue("stack_layer", "Stack layer must be 1 or greater."))
    return issues


def decide_stacked_pull_request_review(
    context: StackedPullRequestReviewContext,
) -> StackedPullRequestReviewDecision:
    """Decide stacked PR approval and merge readiness without resolving conflicts."""

    validation_issues = validate_stacked_pull_request_review_context(context)
    approval_blockers = [f"{issue.field}: {issue.message}" for issue in validation_issues]
    merge_blockers: list[str] = []
    layer_local_comments = list(context.layer_local_findings)
    lower_layer_change_comments = list(context.lower_layer_change_findings)

    if context.expected_base_branch.strip() and context.base_branch.strip() != context.expected_base_branch.strip():
        approval_blockers.append("PR base branch does not match the configured stack base branch.")
    if not context.jira_pr_link_visible:
        approval_blockers.append("Jira story is missing a visible pull request link.")
    if not context.checks_complete:
        approval_blockers.append("Required pull request checks are not complete.")
    elif not context.checks_passed:
        approval_blockers.append("Required pull request checks are failing.")
    if context.stack_layer > 1 and not context.required_lower_layer_approved:
        approval_blockers.append("Required lower-layer approval is missing.")

    stale_rebase_required = _stacked_review_rebase_required(context)
    if stale_rebase_required:
        approval_blockers.append("Lower stack layer changed after review; Developer Agent must rebase this layer.")
        lower_layer_change_comments.append(
            "Lower-layer change: reviewed lower-layer SHA no longer matches the current lower-layer SHA."
        )

    for conflict in context.detected_conflicts:
        conflict_text = conflict.strip()
        if not conflict_text:
            continue
        approval_blockers.append(f"Conflict must return to Developer Agent: {conflict_text}")
        layer_local_comments.append(f"Layer-local conflict handoff: {conflict_text}")

    merge_strategy = _stacked_review_merge_strategy(context)
    approval_ready = not approval_blockers
    if approval_ready:
        if (
            merge_strategy == StackedReviewMergeStrategy.BOTTOM_UP
            and context.stack_layer > 1
            and not context.required_lower_layer_merged
        ):
            merge_blockers.append("Lower stack layer must merge before this layer can merge.")
    else:
        merge_blockers.append("Approval blockers must be resolved before merge.")

    merge_ready = approval_ready and not merge_blockers
    record = StackedPullRequestLayerReviewRecord(
        review_record_id=context.review_record_id.strip(),
        jira_issue_key=context.jira_issue_key.strip(),
        pull_request_url=context.pull_request_url.strip(),
        pull_request_number=context.pull_request_number,
        stack_id=context.stack_id.strip(),
        lane_id=context.lane_id.strip(),
        stack_layer=context.stack_layer,
        base_branch=context.base_branch.strip(),
        head_branch=context.head_branch.strip(),
        reviewed_base_sha=context.reviewed_base_sha.strip(),
        reviewed_head_sha=context.reviewed_head_sha.strip(),
        merge_strategy=merge_strategy,
        approval_ready=approval_ready,
        merge_ready=merge_ready,
        stale_rebase_required=stale_rebase_required,
    )
    return StackedPullRequestReviewDecision(
        review_record=record,
        approval_ready=approval_ready,
        merge_ready=merge_ready,
        merge_strategy=merge_strategy,
        stale_rebase_required=stale_rebase_required,
        approval_blockers=tuple(approval_blockers),
        merge_blockers=tuple(merge_blockers),
        layer_local_comments=tuple(layer_local_comments),
        lower_layer_change_comments=tuple(lower_layer_change_comments),
    )


def render_stacked_pull_request_review_comment(decision: StackedPullRequestReviewDecision) -> str:
    """Render Jira-visible stacked review status with layer-local separation."""

    record = decision.review_record
    lines = [
        f"Stacked PR review for {record.jira_issue_key}:",
        "",
        f"PR: {record.pull_request_url}",
        f"Stack: {record.stack_id} / lane {record.lane_id} / layer {record.stack_layer}",
        f"Base: {record.base_branch} ({record.reviewed_base_sha})",
        f"Head: {record.head_branch} ({record.reviewed_head_sha})",
        f"Merge strategy: {decision.merge_strategy.value}",
        f"Approval ready: {'yes' if decision.approval_ready else 'no'}",
        f"Merge ready: {'yes' if decision.merge_ready else 'no'}",
    ]
    if decision.approval_blockers:
        lines.extend(["", "Approval blockers:"])
        lines.extend(f"- {blocker}" for blocker in decision.approval_blockers)
    if decision.merge_blockers:
        lines.extend(["", "Merge blockers:"])
        lines.extend(f"- {blocker}" for blocker in decision.merge_blockers)
    if decision.layer_local_comments:
        lines.extend(["", f"{StackedReviewCommentScope.LAYER_LOCAL.value} comments:"])
        lines.extend(f"- {comment}" for comment in decision.layer_local_comments)
    if decision.lower_layer_change_comments:
        lines.extend(["", f"{StackedReviewCommentScope.LOWER_LAYER_CHANGE.value} comments:"])
        lines.extend(f"- {comment}" for comment in decision.lower_layer_change_comments)
    return "\n".join(lines).strip()


def stacked_review_layer_record_to_dict(record: StackedPullRequestLayerReviewRecord) -> dict[str, object]:
    """Convert a stacked PR review layer record into durable JSON-ready data."""

    return {
        "review_record_id": record.review_record_id,
        "jira_issue_key": record.jira_issue_key,
        "pull_request_url": record.pull_request_url,
        "pull_request_number": record.pull_request_number,
        "stack_id": record.stack_id,
        "lane_id": record.lane_id,
        "stack_layer": record.stack_layer,
        "base_branch": record.base_branch,
        "head_branch": record.head_branch,
        "reviewed_base_sha": record.reviewed_base_sha,
        "reviewed_head_sha": record.reviewed_head_sha,
        "merge_strategy": record.merge_strategy.value,
        "approval_ready": record.approval_ready,
        "merge_ready": record.merge_ready,
        "stale_rebase_required": record.stale_rebase_required,
    }


def jira_status_after_review_merge() -> str:
    """Return target Jira status after Review Agent merge and Tester handoff."""

    return REVIEW_MERGED_JIRA_STATUS


def format_pull_request_review_issues(issues: Sequence[PullRequestReviewIssue]) -> str:
    """Format review workflow validation issues."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _require_text(issues: list[PullRequestReviewIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(PullRequestReviewIssue(field, "Value is required."))


def _replace_record_decision(record: ReviewRecord, decision: ReviewDecision) -> ReviewRecord:
    return ReviewRecord(
        id=record.id,
        jira_issue_key=record.jira_issue_key,
        pull_request_url=record.pull_request_url,
        pull_request_number=record.pull_request_number,
        head_branch=record.head_branch,
        base_branch=record.base_branch,
        head_sha=record.head_sha,
        reviewer=record.reviewer,
        scope=record.scope,
        routing=record.routing,
        final_decision=decision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        findings=record.findings,
        requested_changes=record.requested_changes,
        developer_responses=record.developer_responses,
    )


def _stacked_review_rebase_required(context: StackedPullRequestReviewContext) -> bool:
    return (
        bool(context.lower_layer_recorded_head_sha.strip())
        and bool(context.lower_layer_current_head_sha.strip())
        and context.lower_layer_recorded_head_sha.strip() != context.lower_layer_current_head_sha.strip()
    )


def _stacked_review_merge_strategy(
    context: StackedPullRequestReviewContext,
) -> StackedReviewMergeStrategy:
    if context.merge_queue_supported and context.branch_protection_supports_stack_merge:
        return StackedReviewMergeStrategy.QUEUED_STACK_MERGE
    return StackedReviewMergeStrategy.BOTTOM_UP


def _fallback_diagnostic(provider_status_code: int | None, provider_message: str) -> str:
    message = provider_message.strip()
    if provider_status_code == 422:
        return "formal GitHub approval was rejected as unprocessable; approval was published as PR comment fallback"
    if provider_status_code == 403:
        return "formal GitHub approval was blocked by permissions; check repository token or app access"
    if provider_status_code == 401:
        return "formal GitHub approval was blocked by authentication; refresh GitHub credentials"
    if provider_status_code is not None:
        return f"formal GitHub approval failed with HTTP {provider_status_code}" + (f": {message}" if message else "")
    return message or "formal GitHub approval publication status was not reported"
